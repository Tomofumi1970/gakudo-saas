"""POST /invoices/{household_id}/{billing_unit}/issue — 請求書発行。

DRAFT → ISSUED に遷移し、世帯の主担当保護者(PRIMARY_GUARDIAN)宛にメール送信。
SES sandbox 中は受信側 verified が必須(本番化で解除)。
"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    path_param,
    response,
    table,
    write_audit_log,
)
from common.mailer import send_email


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can issue invoices")

    household_id = path_param(event, "household_id")
    billing_unit = path_param(event, "billing_unit")
    # path で "MONTH#2026-05" のようなスラッシュ無しの billing_unit を渡す前提
    # 将来必要なら URL エンコード対応(現状 # は許容される)

    pk = f"{caller.org_id}#{household_id}"
    res = table("INVOICES_TABLE").get_item(
        Key={"org_household": pk, "billing_unit": billing_unit}
    )
    if "Item" not in res:
        raise HttpError(404, "invoice not found")
    invoice = res["Item"]

    if invoice.get("status") in ("ISSUED", "PAID"):
        raise HttpError(409, f"invoice already {invoice.get('status')}")

    now = iso_now()
    table("INVOICES_TABLE").update_item(
        Key={"org_household": pk, "billing_unit": billing_unit},
        UpdateExpression=(
            "SET #s = :s, issued_at = :t, issued_by = :u"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "ISSUED",
            ":t": now,
            ":u": caller.user_id,
        },
    )

    # 主担当保護者のメールアドレスを取得
    members = table("MEMBERS_TABLE").query(
        IndexName="gsi1-household-type",
        KeyConditionExpression=Key("household_id").eq(household_id),
    )
    primary = next(
        (
            m
            for m in members.get("Items", [])
            if m.get("org_id") == caller.org_id
            and m.get("status") == "PRIMARY_GUARDIAN"
            and m.get("email")
        ),
        None,
    )

    mail_status = "skipped: no primary guardian email"
    if primary:
        total = int(float(invoice.get("total", 0)))
        subject = f"【ひまわりクラブ】請求書発行のお知らせ({billing_unit})"
        body = (
            f"{primary.get('family_name', '')}様\n\n"
            f"下記の通り請求書を発行いたしました。\n\n"
            f"請求対象: {billing_unit}\n"
            f"金額: ¥{total:,}\n"
            f"明細件数: {invoice.get('line_count', 0)}件\n\n"
            f"詳細はマイページにてご確認ください。\n"
            f"何かご不明な点があればご連絡ください。\n"
        )
        try:
            send_email(to=primary["email"], subject=subject, body_text=body)
            mail_status = "sent"
        except Exception as e:  # noqa: BLE001
            mail_status = f"failed: {e}"

    write_audit_log(
        "invoice",
        f"{household_id}#{billing_unit}",
        "issue",
        caller,
        after={"status": "ISSUED", "mail_status": mail_status},
    )

    return response(
        200,
        {
            "household_id": household_id,
            "billing_unit": billing_unit,
            "status": "ISSUED",
            "mail_status": mail_status,
        },
    )


handler = handler_wrapper(_impl)

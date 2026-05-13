"""POST /invoices/{household_id}/{billing_unit}/mark-paid — 入金消込。

決済機能を持たない設計(spec.md §5.4)のため、通帳突合の結果として
会計役員/管理者が手動で「PAID」に遷移させるためのフラグ更新API。

Body:
  paid_at (str)        任意(ISO日時、省略時は現在時刻)
  paid_amount (number) 任意(部分入金時の記録用)
  note (str)           任意
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    parse_body,
    path_param,
    response,
    table,
    write_audit_log,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    # 入金消込ロールに該当する権限
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can mark paid")

    household_id = path_param(event, "household_id")
    billing_unit = path_param(event, "billing_unit")
    body = parse_body(event)

    pk = f"{caller.org_id}#{household_id}"
    res = table("INVOICES_TABLE").get_item(
        Key={"org_household": pk, "billing_unit": billing_unit}
    )
    if "Item" not in res:
        raise HttpError(404, "invoice not found")
    invoice = res["Item"]
    if invoice.get("status") == "PAID":
        raise HttpError(409, "invoice already paid")

    now = iso_now()
    paid_at = body.get("paid_at") or now
    update_expr = (
        "SET #s = :s, paid_at = :p, paid_by = :u, mark_paid_at = :t"
    )
    expr_vals: dict[str, Any] = {
        ":s": "PAID",
        ":p": paid_at,
        ":u": caller.user_id,
        ":t": now,
    }

    paid_amount = body.get("paid_amount")
    if paid_amount is not None:
        try:
            expr_vals[":pa"] = Decimal(str(paid_amount))
            update_expr += ", paid_amount = :pa"
        except Exception as e:
            raise HttpError(400, f"invalid paid_amount: {e}") from e

    note = body.get("note")
    if note:
        expr_vals[":n"] = note
        update_expr += ", paid_note = :n"

    table("INVOICES_TABLE").update_item(
        Key={"org_household": pk, "billing_unit": billing_unit},
        UpdateExpression=update_expr,
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues=expr_vals,
    )

    write_audit_log(
        "invoice",
        f"{household_id}#{billing_unit}",
        "mark_paid",
        caller,
        before={"status": invoice.get("status")},
        after={"status": "PAID", "paid_at": paid_at},
    )

    return response(
        200,
        {
            "household_id": household_id,
            "billing_unit": billing_unit,
            "status": "PAID",
            "paid_at": paid_at,
        },
    )


handler = handler_wrapper(_impl)

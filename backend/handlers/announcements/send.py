"""POST /announcements/{announcement_id}/send — お知らせをメール一斉配信。

処理:
1) お知らせを取得、status を SENDING に
2) target_audience に応じて宛先メールアドレスを収集
3) 各保護者(PRIMARY_GUARDIAN で email 持ち)にメール送信
4) status を SENT に、recipient_count / sent_at を記録
5) SES 失敗は記録するが処理は継続(再送は呼び出し側)
"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

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
from common.mailer import send_email


def _collect_recipient_emails(
    caller: Caller, audience: str, target_household_ids: list[str] | None
) -> list[str]:
    """対象保護者のメールアドレスを収集。

    MVP では ALL と HOUSEHOLDS のみ実装。HIGH_GRADE/LOW_GRADE は将来。
    """
    # 全PRIMARY_GUARDIANメンバーをスキャンするのは非効率だが、規模100名前提なら許容
    # 本来は GSI(status=PRIMARY_GUARDIAN) を用意すべきだが Phase 6.1 では scan で簡略
    res = table("MEMBERS_TABLE").scan(
        FilterExpression=Key("org_id").eq(caller.org_id)
        & Key("status").eq("PRIMARY_GUARDIAN"),
    )
    members = res.get("Items", [])
    if audience == "HOUSEHOLDS" and target_household_ids:
        ids = set(target_household_ids)
        members = [m for m in members if m.get("household_id") in ids]
    return [m["email"] for m in members if m.get("email")]


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can send announcements")

    announcement_id = path_param(event, "announcement_id")
    _body = parse_body(event)  # 将来 dryRun フラグ等

    res = table("ANNOUNCEMENTS_TABLE").get_item(
        Key={"org_id": caller.org_id, "announcement_id": announcement_id}
    )
    if "Item" not in res:
        raise HttpError(404, "announcement not found")
    a = res["Item"]
    if a.get("status") == "SENT":
        raise HttpError(409, "already sent")

    emails = _collect_recipient_emails(
        caller, a["target_audience"], a.get("target_household_ids")
    )

    now = iso_now()
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for to_addr in emails:
        try:
            send_email(
                to=to_addr,
                subject=f"【ひまわりクラブ】{a['title']}",
                body_text=a["body"],
            )
            succeeded.append(to_addr)
        except Exception as e:  # noqa: BLE001
            failed.append({"to": to_addr, "error": str(e)})

    table("ANNOUNCEMENTS_TABLE").update_item(
        Key={"org_id": caller.org_id, "announcement_id": announcement_id},
        UpdateExpression=(
            "SET #s = :s, sent_at = :t, sent_by = :u, recipient_count = :c, "
            "failed_count = :f"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "SENT",
            ":t": now,
            ":u": caller.user_id,
            ":c": len(succeeded),
            ":f": len(failed),
        },
    )
    write_audit_log(
        "announcement",
        announcement_id,
        "send",
        caller,
        after={"recipient_count": len(succeeded), "failed_count": len(failed)},
    )
    return response(
        200,
        {
            "announcement_id": announcement_id,
            "status": "SENT",
            "recipient_count": len(succeeded),
            "failed_count": len(failed),
            "failed": failed,
        },
    )


handler = handler_wrapper(_impl)

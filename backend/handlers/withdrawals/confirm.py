"""POST /withdrawals/{withdrawal_id}/confirm — 退所を確定。

Member の status を WITHDRAWN(または GRADUATED 指定可)に更新。
"""
from __future__ import annotations

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
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can confirm withdrawals")

    withdrawal_id = path_param(event, "withdrawal_id")
    body = parse_body(event)
    new_status = body.get("new_status", "WITHDRAWN")
    if new_status not in ("WITHDRAWN", "GRADUATED"):
        raise HttpError(400, "new_status must be WITHDRAWN or GRADUATED")

    res = table("WITHDRAWALS_TABLE").get_item(
        Key={"org_id": caller.org_id, "withdrawal_id": withdrawal_id}
    )
    if "Item" not in res:
        raise HttpError(404, "withdrawal not found")
    w = res["Item"]
    if w.get("status") == "CONFIRMED":
        raise HttpError(409, "already confirmed")

    now = iso_now()
    # Member の status を更新
    table("MEMBERS_TABLE").update_item(
        Key={"org_id": caller.org_id, "member_id": w["member_id"]},
        UpdateExpression=(
            "SET #s = :s, withdrawn_at = :t, updated_at = :t, updated_by = :u"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": new_status,
            ":t": now,
            ":u": caller.user_id,
        },
    )
    table("WITHDRAWALS_TABLE").update_item(
        Key={"org_id": caller.org_id, "withdrawal_id": withdrawal_id},
        UpdateExpression=(
            "SET #s = :s, confirmed_at = :t, confirmed_by = :u, "
            "applied_member_status = :ms"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "CONFIRMED",
            ":t": now,
            ":u": caller.user_id,
            ":ms": new_status,
        },
    )
    write_audit_log(
        "withdrawal",
        withdrawal_id,
        "confirm",
        caller,
        after={"member_id": w["member_id"], "new_status": new_status},
    )
    return response(
        200,
        {
            "withdrawal_id": withdrawal_id,
            "status": "CONFIRMED",
            "member_id": w["member_id"],
            "member_status": new_status,
        },
    )


handler = handler_wrapper(_impl)

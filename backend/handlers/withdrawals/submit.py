"""POST /withdrawals — 退所届を提出。

保護者(自世帯の児童のみ)または staff(代理)が提出可能。

Body:
  household_id (str)              必須(parent は自分の household_id と一致必須)
  member_id (str)                 必須(退所する児童の member_id)
  last_attendance_date (str)      必須
  reason (str)                    任意
"""
from __future__ import annotations

from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    new_id,
    parse_body,
    response,
    table,
    write_audit_log,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    body = parse_body(event)
    household_id = body.get("household_id")
    member_id = body.get("member_id")
    last_date = body.get("last_attendance_date")
    if not household_id or not member_id or not last_date:
        raise HttpError(400, "household_id, member_id, last_attendance_date are required")

    # parent は自世帯のみ
    if caller.user_type == "parent" and caller.household_id != household_id:
        raise HttpError(403, "parent can only submit withdrawal for own household")
    if caller.user_type not in ("staff", "operator", "parent"):
        raise HttpError(403, "not allowed")

    # メンバーの存在確認
    m_res = table("MEMBERS_TABLE").get_item(
        Key={"org_id": caller.org_id, "member_id": member_id}
    )
    if "Item" not in m_res:
        raise HttpError(404, "member not found")
    if m_res["Item"].get("household_id") != household_id:
        raise HttpError(400, "member does not belong to the given household")

    withdrawal_id = new_id()
    now = iso_now()
    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "withdrawal_id": withdrawal_id,
        "household_id": household_id,
        "member_id": member_id,
        "member_name": f"{m_res['Item'].get('family_name','')} {m_res['Item'].get('given_name','')}".strip(),
        "last_attendance_date": last_date,
        "status": "SUBMITTED",
        "submitted_at": now,
        "submitted_by": caller.user_id,
    }
    reason = body.get("reason")
    if reason:
        item["reason"] = reason
    table("WITHDRAWALS_TABLE").put_item(Item=item)
    write_audit_log("withdrawal", withdrawal_id, "submit", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

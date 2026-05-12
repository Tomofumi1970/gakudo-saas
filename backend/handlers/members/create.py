"""POST /households/{household_id}/members — 世帯にメンバーを追加。

メンバーは spec.md §4.2 のステータス区分に従う:
  児童: PROSPECTIVE | ACTIVE | GRADUATED | WITHDRAWN
  兄弟: PRESCHOOL_GUEST | ALUMNI_GUEST
  保護者: PRIMARY_GUARDIAN | SECONDARY_GUARDIAN | EMERGENCY_CONTACT
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
    path_param,
    response,
    table,
    write_audit_log,
)

_VALID_STATUSES = {
    "PROSPECTIVE",
    "ACTIVE",
    "GRADUATED",
    "WITHDRAWN",
    "PRESCHOOL_GUEST",
    "ALUMNI_GUEST",
    "PRIMARY_GUARDIAN",
    "SECONDARY_GUARDIAN",
    "EMERGENCY_CONTACT",
}

_VALID_MEMBER_TYPES = {"child", "sibling", "guardian", "contact"}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can create members")

    household_id = path_param(event, "household_id")
    body = parse_body(event)

    member_type = body.get("member_type")
    status = body.get("status")
    family_name = body.get("family_name")
    given_name = body.get("given_name")

    if member_type not in _VALID_MEMBER_TYPES:
        raise HttpError(400, f"invalid member_type: {member_type}")
    if status not in _VALID_STATUSES:
        raise HttpError(400, f"invalid status: {status}")
    if not family_name or not given_name:
        raise HttpError(400, "family_name and given_name are required")

    # 世帯の存在確認(同テナント内)
    house = table("HOUSEHOLDS_TABLE").get_item(
        Key={"org_id": caller.org_id, "household_id": household_id}
    )
    if "Item" not in house:
        raise HttpError(404, "household not found")

    member_id = new_id()
    now = iso_now()
    # GSI gsi2-status-grade のキー grade は空不可。
    # 学年が無いメンバー(保護者等)は grade 属性自体を含めず、GSIから除外する。
    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "member_id": member_id,
        "household_id": household_id,
        "member_type": member_type,
        "status": status,
        "family_name": family_name,
        "given_name": given_name,
        "photo_consent": bool(body.get("photo_consent", False)),
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    # 任意フィールド: 値があるときだけ入れる(空文字はGSI制約とノイズの両方で不利)
    for key in (
        "family_name_kana",
        "given_name_kana",
        "date_of_birth",
        "gender",
        "grade",
        "email",
        "phone",
        "allergies",
        "considerations",
    ):
        v = body.get(key)
        if v:
            item[key] = v
    table("MEMBERS_TABLE").put_item(Item=item)
    write_audit_log("member", member_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

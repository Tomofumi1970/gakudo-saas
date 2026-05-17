"""PATCH /members/{member_id} — メンバー情報の部分更新。

更新可能: family_name, given_name, family_name_kana, given_name_kana,
         date_of_birth, gender, grade, email, phone, allergies,
         considerations, photo_consent, status, member_type
更新不可: org_id, member_id, household_id, created_at, created_by

注意:
- status / member_type を変更した結果 grade が空文字になる場合があるため、
  空文字をセットしようとした場合は属性自体を削除する(GSI 制約)
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

_VALID_STATUSES = {
    "PROSPECTIVE", "ACTIVE", "GRADUATED", "WITHDRAWN",
    "PRESCHOOL_GUEST", "ALUMNI_GUEST",
    "PRIMARY_GUARDIAN", "SECONDARY_GUARDIAN", "EMERGENCY_CONTACT",
}
_VALID_TYPES = {"child", "sibling", "guardian", "contact"}
_UPDATABLE_TEXT = (
    "family_name", "given_name",
    "family_name_kana", "given_name_kana",
    "date_of_birth", "gender", "grade",
    "email", "phone", "allergies", "considerations",
)
_UPDATABLE_BOOL = ("photo_consent",)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can update members")

    member_id = path_param(event, "member_id")
    body = parse_body(event)

    before_res = table("MEMBERS_TABLE").get_item(
        Key={"org_id": caller.org_id, "member_id": member_id}
    )
    if "Item" not in before_res:
        raise HttpError(404, "member not found")
    before = before_res["Item"]

    new_status = body.get("status")
    if new_status is not None and new_status not in _VALID_STATUSES:
        raise HttpError(400, f"invalid status: {new_status}")
    new_type = body.get("member_type")
    if new_type is not None and new_type not in _VALID_TYPES:
        raise HttpError(400, f"invalid member_type: {new_type}")

    # SET 句と REMOVE 句を分けて構築
    sets: list[str] = ["updated_at = :t", "updated_by = :u"]
    removes: list[str] = []
    values: dict[str, Any] = {":t": iso_now(), ":u": caller.user_id}
    names: dict[str, str] = {}

    def emit(key: str, val: Any) -> None:
        # 空文字なら削除、それ以外なら SET
        nk = f"#n_{key}"
        vk = f":v_{key}"
        names[nk] = key
        if val == "" or val is None:
            removes.append(nk)
        else:
            values[vk] = val
            sets.append(f"{nk} = {vk}")

    if new_type is not None:
        emit("member_type", new_type)
    if new_status is not None:
        emit("status", new_status)
    for k in _UPDATABLE_TEXT:
        if k in body:
            emit(k, body[k])
    for k in _UPDATABLE_BOOL:
        if k in body:
            v = bool(body[k])
            nk = f"#n_{k}"
            vk = f":v_{k}"
            names[nk] = k
            values[vk] = v
            sets.append(f"{nk} = {vk}")

    if len(sets) <= 2 and not removes:
        raise HttpError(400, "no updatable fields provided")

    upd = "SET " + ", ".join(sets)
    if removes:
        upd += " REMOVE " + ", ".join(removes)

    res = table("MEMBERS_TABLE").update_item(
        Key={"org_id": caller.org_id, "member_id": member_id},
        UpdateExpression=upd,
        ExpressionAttributeNames=names if names else None,
        ExpressionAttributeValues=values if values else None,
        ReturnValues="ALL_NEW",
    )
    after = res.get("Attributes", {})
    write_audit_log(
        "member", member_id, "update", caller,
        before={k: before.get(k) for k in (list(_UPDATABLE_TEXT) + list(_UPDATABLE_BOOL) + ["status", "member_type"]) if k in body},
        after={k: v for k, v in body.items()},
    )
    return response(200, after)


handler = handler_wrapper(_impl)

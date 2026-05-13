"""POST /staff — 指導員(職員)登録。

Body:
  family_name, given_name           必須
  role                              STAFF_HEAD | STAFF_SUB_HEAD | STAFF_FULL | STAFF_PART
  hired_at (YYYY-MM-DD)             必須
  email, phone, nickname            任意
  qualifications (list[str])        任意(放課後児童支援員、食品衛生責任者など)
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

_VALID_ROLES = {"STAFF_HEAD", "STAFF_SUB_HEAD", "STAFF_FULL", "STAFF_PART"}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can register staff")

    body = parse_body(event)
    family_name = body.get("family_name")
    given_name = body.get("given_name")
    role = body.get("role")
    hired_at = body.get("hired_at")
    if not family_name or not given_name:
        raise HttpError(400, "family_name and given_name are required")
    if role not in _VALID_ROLES:
        raise HttpError(400, f"invalid role: {role}")
    if not hired_at:
        raise HttpError(400, "hired_at is required")

    staff_id = new_id()
    now = iso_now()
    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "staff_id": staff_id,
        "family_name": family_name,
        "given_name": given_name,
        "role": role,
        "hired_at": hired_at,
        "status": "ACTIVE",
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    for k in ("nickname", "email", "phone", "qualifications"):
        v = body.get(k)
        if v:
            item[k] = v

    table("STAFF_TABLE").put_item(Item=item)
    write_audit_log("staff", staff_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

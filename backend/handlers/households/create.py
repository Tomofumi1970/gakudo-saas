"""POST /households — 世帯を新規作成。

施設管理者・職員のみ実行可(MVPでは user_type を見るのみ、詳細なロール検証は将来Phase)。
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
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can create households")

    body = parse_body(event)
    address = body.get("address")
    phone = body.get("phone")
    note = body.get("note")
    if not address:
        raise HttpError(400, "address is required")

    household_id = new_id()
    now = iso_now()
    item = {
        "org_id": caller.org_id,
        "household_id": household_id,
        "address": address,
        "phone": phone or "",
        "note": note or "",
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    table("HOUSEHOLDS_TABLE").put_item(Item=item)
    write_audit_log("household", household_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

"""POST /applications — 入所申込を送信。

保護者ロールでも staff でも送信可能(スタッフが代理入力するケースも対応)。
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
    required = ["child_family_name", "child_given_name", "child_dob",
                "parent_name", "parent_email", "parent_phone", "address",
                "requested_start_date"]
    missing = [k for k in required if not body.get(k)]
    if missing:
        raise HttpError(400, f"missing required fields: {missing}")

    application_id = new_id()
    now = iso_now()
    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "application_id": application_id,
        "status": "SUBMITTED",
        "submitted_at": now,
        "submitted_by": caller.user_id,
    }
    for k in required + ["child_grade", "notes", "siblings_in_school"]:
        v = body.get(k)
        if v is not None and v != "":
            item[k] = v

    table("APPLICATIONS_TABLE").put_item(Item=item)
    write_audit_log("application", application_id, "submit", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

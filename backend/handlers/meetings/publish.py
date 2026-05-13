"""POST /meetings/{minute_id}/publish — 議事録を PUBLISHED に。"""
from __future__ import annotations

from typing import Any

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


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can publish meeting minutes")

    minute_id = path_param(event, "minute_id")
    res = table("MEETING_MINUTES_TABLE").get_item(
        Key={"org_id": caller.org_id, "minute_id": minute_id}
    )
    if "Item" not in res:
        raise HttpError(404, "minute not found")
    if res["Item"].get("status") == "PUBLISHED":
        raise HttpError(409, "already published")

    now = iso_now()
    table("MEETING_MINUTES_TABLE").update_item(
        Key={"org_id": caller.org_id, "minute_id": minute_id},
        UpdateExpression="SET #s = :s, published_at = :t, published_by = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "PUBLISHED",
            ":t": now,
            ":u": caller.user_id,
        },
    )
    write_audit_log(
        "meeting_minute", minute_id, "publish", caller, after={"status": "PUBLISHED"}
    )
    return response(200, {"minute_id": minute_id, "status": "PUBLISHED"})


handler = handler_wrapper(_impl)

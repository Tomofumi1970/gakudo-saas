"""POST /meetings — 議事録を作成(DRAFT)。

Body:
  meeting_type    必須(EXAMPLE | OFFICERS_MEETING | RUNNING_COMMITTEE | GENERAL_ASSEMBLY)
  meeting_date    必須(YYYY-MM-DD)
  title           必須
  agenda          任意(議題)
  decisions       任意(決定事項)
  body            任意(詳細議事内容)
  attendees       任意(list[str])
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

_VALID_TYPES = {
    "EXAMPLE",
    "OFFICERS_MEETING",
    "RUNNING_COMMITTEE",
    "GENERAL_ASSEMBLY",
}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can create meeting minutes")

    body = parse_body(event)
    mtype = body.get("meeting_type")
    mdate = body.get("meeting_date")
    title = body.get("title")
    if mtype not in _VALID_TYPES:
        raise HttpError(400, f"invalid meeting_type: {mtype}")
    if not mdate or not title:
        raise HttpError(400, "meeting_date and title are required")

    minute_id = f"{mdate}#{new_id()[:8]}"
    now = iso_now()
    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "minute_id": minute_id,
        "meeting_type": mtype,
        "meeting_date": mdate,
        "title": title,
        "status": "DRAFT",
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    for k in ("agenda", "decisions", "body"):
        v = body.get(k)
        if v:
            item[k] = v
    attendees = body.get("attendees")
    if attendees:
        item["attendees"] = attendees

    table("MEETING_MINUTES_TABLE").put_item(Item=item)
    write_audit_log("meeting_minute", minute_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

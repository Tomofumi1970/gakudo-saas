"""POST /announcements — お知らせを作成(DRAFT)。

Body:
  title (str)            必須
  body (str)             必須
  type (str)             SCHOOL_CLOSURE | WEATHER_WARNING | EVENT_INVITE | GENERAL
  target_audience (str)  ALL | HOUSEHOLDS | HIGH_GRADE | LOW_GRADE(初期はALLのみ機能、他は将来)
  target_household_ids   任意(target_audience=HOUSEHOLDSのとき)
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

_VALID_TYPES = {"SCHOOL_CLOSURE", "WEATHER_WARNING", "EVENT_INVITE", "GENERAL"}
_VALID_AUDIENCE = {"ALL", "HOUSEHOLDS", "HIGH_GRADE", "LOW_GRADE"}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can create announcements")

    body = parse_body(event)
    title = body.get("title")
    text = body.get("body")
    atype = body.get("type", "GENERAL")
    audience = body.get("target_audience", "ALL")

    if not title or not text:
        raise HttpError(400, "title and body are required")
    if atype not in _VALID_TYPES:
        raise HttpError(400, f"invalid type: {atype}")
    if audience not in _VALID_AUDIENCE:
        raise HttpError(400, f"invalid target_audience: {audience}")

    announcement_id = new_id()
    now = iso_now()
    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "announcement_id": announcement_id,
        "title": title,
        "body": text,
        "type": atype,
        "target_audience": audience,
        "status": "DRAFT",
        "created_at": now,
        "created_by": caller.user_id,
    }
    tids = body.get("target_household_ids")
    if tids:
        item["target_household_ids"] = tids

    table("ANNOUNCEMENTS_TABLE").put_item(Item=item)
    write_audit_log("announcement", announcement_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

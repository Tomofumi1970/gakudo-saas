"""POST /events — イベント作成。

Body:
  name (str)              必須(例: ファミリーキャンプ2026)
  event_date (str)        必須(YYYY-MM-DD)
  billing_unit (str)      任意(省略時は EVENT#<event_id>)
  description (str)       任意
  age_pricing (dict)      任意(年齢区分別の単価メモ。spec.md §5.5の参考情報)
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
        raise HttpError(403, "only staff can create events")

    body = parse_body(event)
    name = body.get("name")
    event_date = body.get("event_date")
    if not name:
        raise HttpError(400, "name is required")
    if not event_date:
        raise HttpError(400, "event_date is required")

    event_id = new_id()
    now = iso_now()
    billing_unit = body.get("billing_unit") or f"EVENT#{event_id}"

    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "event_id": event_id,
        "name": name,
        "event_date": event_date,
        "billing_unit": billing_unit,
        "status": "PLANNING",  # PLANNING -> OPEN -> CLOSED -> SETTLED
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    for k in ("description", "age_pricing"):
        v = body.get(k)
        if v:
            item[k] = v

    table("EVENTS_TABLE").put_item(Item=item)
    write_audit_log("event", event_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

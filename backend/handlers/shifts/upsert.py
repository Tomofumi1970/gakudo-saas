"""POST /shifts — 指定日のシフトを一括 upsert。

Body:
  date (YYYY-MM-DD)        必須
  entries (list[dict])     必須。各要素:
    staff_id (str)         必須
    shift_type (str)       MORNING | AFTERNOON | EVENING | FULL | ONCALL
    planned_start (HH:MM)  任意
    planned_end (HH:MM)    任意
    break_minutes (int)    任意
    note (str)             任意
"""
from __future__ import annotations

from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    parse_body,
    response,
    table,
    write_audit_log,
)

_VALID_TYPES = {"MORNING", "AFTERNOON", "EVENING", "FULL", "ONCALL"}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can edit shifts")

    body = parse_body(event)
    date = body.get("date")
    entries = body.get("entries") or []
    if not date:
        raise HttpError(400, "date is required")
    if not isinstance(entries, list) or not entries:
        raise HttpError(400, "entries must be a non-empty array")

    now = iso_now()
    pk = f"{caller.org_id}#{date}"
    written: list[dict[str, Any]] = []
    tbl = table("SHIFTS_TABLE")

    with tbl.batch_writer() as batch:
        for e in entries:
            sid = e.get("staff_id")
            stype = e.get("shift_type")
            if not sid:
                raise HttpError(400, "staff_id is required for each entry")
            if stype not in _VALID_TYPES:
                raise HttpError(400, f"invalid shift_type: {stype}")
            item: dict[str, Any] = {
                "org_date": pk,
                "staff_id": sid,
                "org_id": caller.org_id,
                "work_date": date,
                "org_staff": f"{caller.org_id}#{sid}",
                "shift_type": stype,
                "status": "PLANNED",
                "updated_at": now,
                "updated_by": caller.user_id,
            }
            for k in ("planned_start", "planned_end", "break_minutes", "note"):
                v = e.get(k)
                if v is not None and v != "":
                    item[k] = v
            batch.put_item(Item=item)
            written.append(item)

    write_audit_log(
        "shift", f"{date}#bulk", "upsert", caller, after={"count": len(written), "date": date}
    )
    return response(200, {"date": date, "count": len(written), "entries": written})


handler = handler_wrapper(_impl)

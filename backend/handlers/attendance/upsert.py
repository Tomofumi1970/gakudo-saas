"""POST /attendance — 出席記録を一括登録/更新(同日同メンバーは上書き)。

Body:
  date (YYYY-MM-DD)   必須
  entries (list[dict]) 必須。各要素:
    member_id (str)   必須
    status (str)      PRESENT | ABSENT | EARLY_LEAVE | LATE | LATE_LEAVE
    arrival_time      任意(HH:MM)
    departure_time    任意(HH:MM)
    note              任意
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

_VALID_STATUSES = {"PRESENT", "ABSENT", "EARLY_LEAVE", "LATE", "LATE_LEAVE"}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can record attendance")

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
    att = table("ATTENDANCE_TABLE")

    with att.batch_writer() as batch:
        for e in entries:
            member_id = e.get("member_id")
            status = e.get("status")
            if not member_id:
                raise HttpError(400, "member_id is required for each entry")
            if status not in _VALID_STATUSES:
                raise HttpError(400, f"invalid status: {status}")
            item: dict[str, Any] = {
                "org_date": pk,
                "member_id": member_id,
                "org_id": caller.org_id,
                "work_date": date,
                "org_member": f"{caller.org_id}#{member_id}",  # GSI 用
                "status": status,
                "recorded_at": now,
                "recorded_by": caller.user_id,
            }
            for k in ("arrival_time", "departure_time", "note"):
                v = e.get(k)
                if v:
                    item[k] = v
            batch.put_item(Item=item)
            written.append(item)

    write_audit_log(
        "attendance",
        f"{date}#bulk",
        "upsert",
        caller,
        after={"count": len(written), "date": date},
    )
    return response(200, {"date": date, "count": len(written), "entries": written})


handler = handler_wrapper(_impl)

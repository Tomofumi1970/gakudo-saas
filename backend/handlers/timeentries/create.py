"""POST /staff/{staff_id}/timeentries — 勤怠記録の追加。

Body:
  work_date (YYYY-MM-DD)        必須
  hours_regular                 任意(所定内労働、デフォルト0)
  hours_overtime                任意(法定外、深夜以外)
  hours_late_night              任意(22-5時)
  hours_holiday                 任意(法定休日)
  hours_training                任意(研修時間=時間外扱い)
  overnight_stays               任意(キャンプ等の宿泊回数)
  clock_in, clock_out           任意(HH:MM、メモ程度)
  note                          任意
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    new_id,
    parse_body,
    path_param,
    response,
    table,
    write_audit_log,
)

_HOUR_FIELDS = (
    "hours_regular",
    "hours_overtime",
    "hours_late_night",
    "hours_holiday",
    "hours_training",
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can add time entries")

    staff_id = path_param(event, "staff_id")
    body = parse_body(event)
    work_date = body.get("work_date")
    if not work_date:
        raise HttpError(400, "work_date is required")

    staff = table("STAFF_TABLE").get_item(
        Key={"org_id": caller.org_id, "staff_id": staff_id}
    )
    if "Item" not in staff:
        raise HttpError(404, "staff not found")

    entry_id = f"{work_date}#{new_id()[:8]}"
    now = iso_now()
    item: dict[str, Any] = {
        "org_staff": f"{caller.org_id}#{staff_id}",
        "entry_id": entry_id,
        "org_id": caller.org_id,
        "staff_id": staff_id,
        "work_date": work_date,
        "org_date": f"{caller.org_id}#{work_date}",  # GSI 用
        "created_at": now,
        "created_by": caller.user_id,
    }
    for k in _HOUR_FIELDS:
        v = body.get(k)
        if v is not None:
            try:
                item[k] = Decimal(str(v))
            except Exception as e:
                raise HttpError(400, f"invalid {k}: {e}") from e

    overnight = body.get("overnight_stays")
    if overnight is not None:
        item["overnight_stays"] = int(overnight)

    for k in ("clock_in", "clock_out", "note"):
        v = body.get(k)
        if v:
            item[k] = v

    table("TIME_ENTRIES_TABLE").put_item(Item=item)
    write_audit_log("time_entry", entry_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

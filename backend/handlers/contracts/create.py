"""POST /staff/{staff_id}/contracts — 雇用契約を時系列で追加。

賃金規程(別表1)で扱う属性:
  contract_type                   REGULAR | PART_TIME
  base_salary_monthly             REGULAR の月給
  base_hourly_rate                PART_TIME の時給
  monthly_hours_standard          REGULAR の月平均所定労働時間(時給換算)
  commute_allowance_monthly       通勤手当(月額)
  head_allowance_monthly          主任(副主任)手当
  qualification_allowance_monthly 資格手当
  overnight_per_stay              宿泊手当(¥3,000/泊)
  valid_from                      有効開始(YYYY-MM-DD)
  valid_to                        任意(空なら現在の契約)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    parse_body,
    path_param,
    response,
    table,
    write_audit_log,
)

_VALID_TYPES = {"REGULAR", "PART_TIME"}
_DECIMAL_FIELDS = (
    "base_salary_monthly",
    "base_hourly_rate",
    "monthly_hours_standard",
    "commute_allowance_monthly",
    "head_allowance_monthly",
    "qualification_allowance_monthly",
    "overnight_per_stay",
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can edit contracts")

    staff_id = path_param(event, "staff_id")
    body = parse_body(event)

    ctype = body.get("contract_type")
    valid_from = body.get("valid_from")
    if ctype not in _VALID_TYPES:
        raise HttpError(400, f"invalid contract_type: {ctype}")
    if not valid_from:
        raise HttpError(400, "valid_from is required")

    # 指導員存在確認
    staff = table("STAFF_TABLE").get_item(
        Key={"org_id": caller.org_id, "staff_id": staff_id}
    )
    if "Item" not in staff:
        raise HttpError(404, "staff not found")

    now = iso_now()
    item: dict[str, Any] = {
        "org_staff": f"{caller.org_id}#{staff_id}",
        "valid_from": valid_from,
        "org_id": caller.org_id,
        "staff_id": staff_id,
        "contract_type": ctype,
        "created_at": now,
        "created_by": caller.user_id,
    }
    for k in _DECIMAL_FIELDS:
        v = body.get(k)
        if v is not None:
            try:
                item[k] = Decimal(str(v))
            except Exception as e:
                raise HttpError(400, f"invalid {k}: {e}") from e

    valid_to = body.get("valid_to")
    if valid_to:
        item["valid_to"] = valid_to
    note = body.get("note")
    if note:
        item["note"] = note

    table("CONTRACTS_TABLE").put_item(Item=item)
    write_audit_log("contract", f"{staff_id}#{valid_from}", "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

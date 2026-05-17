"""POST /bonuses/calculate — 賞与計算(夏・冬)。

Body:
  year (int)         必須
  season (str)       SUMMER | WINTER 必須
  rate_months (num)  任意(既定 2.0、ひまわり別表1準拠)

基準日:
  SUMMER -> 6/1, WINTER -> 12/1 時点で有効な契約を採用。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

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
from common.payroll import Contract, compute_bonus
from handlers.payroll.calculate import _pick_contract, _contract_from_row


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can run bonus")

    body = parse_body(event)
    year = body.get("year")
    season = body.get("season")
    rate_months = Decimal(str(body.get("rate_months", "2.0")))
    if not year or season not in ("SUMMER", "WINTER"):
        raise HttpError(400, "year and season(SUMMER|WINTER) are required")

    basis_date = f"{year}-06-01" if season == "SUMMER" else f"{year}-12-01"

    # 在籍中の指導員
    staff_res = table("STAFF_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    staff_list = [s for s in staff_res.get("Items", []) if s.get("status") == "ACTIVE"]

    runs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    now = iso_now()
    for s in staff_list:
        sid = s["staff_id"]
        sk = f"{caller.org_id}#{sid}"
        c_res = table("CONTRACTS_TABLE").query(KeyConditionExpression=Key("org_staff").eq(sk))
        contract_row = _pick_contract(c_res.get("Items", []), basis_date)
        if not contract_row:
            skipped.append({"staff_id": sid, "reason": "no active contract"})
            continue
        contract = _contract_from_row(contract_row)
        amount = compute_bonus(contract, season, rate_months)
        bonus_key = f"{year}#{season}"
        item: dict[str, Any] = {
            "org_staff": sk,
            "bonus_key": bonus_key,
            "org_id": caller.org_id,
            "staff_id": sid,
            "year": year,
            "season": season,
            "basis_date": basis_date,
            "rate_months": rate_months,
            "contract_type": contract.contract_type,
            "base_salary_monthly": contract.base_salary_monthly,
            "amount": amount,
            "status": "DRAFT",
            "calculated_at": now,
            "calculated_by": caller.user_id,
        }
        table("BONUS_RUNS_TABLE").put_item(Item=item)
        write_audit_log("bonus_run", f"{sid}#{bonus_key}", "calculate", caller, after=item)
        runs.append(item)

    return response(200, {"year": year, "season": season, "calculated": len(runs), "skipped": skipped, "runs": runs})


handler = handler_wrapper(_impl)

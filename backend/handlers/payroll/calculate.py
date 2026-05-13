"""POST /payroll/calculate — 月次給与計算(自施設の全 ACTIVE 指導員)。

Body:
  period (YYYY-MM)            必須
  staff_ids (list[str])       任意(指定があればその指導員のみ)

処理:
1) 自施設の指導員一覧を取得(active のみ)
2) 各指導員について period 内の TimeEntries を集計
3) 該当時点で有効な契約を 1つ選択(valid_from <= period_start <= valid_to or no valid_to)
4) common.payroll.compute_payroll で総支給額を算出
5) PayrollRuns に1人1行のスナップショットを書き込み
"""
from __future__ import annotations

import re
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
from common.payroll import Contract, TimeAggregate, compute_payroll

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _period_bounds(period: str) -> tuple[str, str]:
    """YYYY-MM -> (YYYY-MM-01, YYYY-MM-31) でDynamoDBの文字列範囲指定に使う簡略境界。"""
    return f"{period}-01", f"{period}-31"


def _pick_contract(contracts: list[dict[str, Any]], period_start: str) -> dict[str, Any] | None:
    """period_start 時点で有効な契約を1つ選ぶ。"""
    eligible = [
        c
        for c in contracts
        if c.get("valid_from", "") <= period_start
        and (not c.get("valid_to") or c["valid_to"] >= period_start)
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda c: c["valid_from"], reverse=True)
    return eligible[0]


def _agg_from_entries(entries: list[dict[str, Any]]) -> TimeAggregate:
    agg = TimeAggregate()
    for e in entries:
        agg.hours_regular += Decimal(str(e.get("hours_regular", 0)))
        agg.hours_overtime += Decimal(str(e.get("hours_overtime", 0)))
        agg.hours_late_night += Decimal(str(e.get("hours_late_night", 0)))
        agg.hours_holiday += Decimal(str(e.get("hours_holiday", 0)))
        agg.hours_training += Decimal(str(e.get("hours_training", 0)))
        agg.overnight_stays += int(e.get("overnight_stays", 0))
    return agg


def _contract_from_row(c: dict[str, Any]) -> Contract:
    return Contract(
        contract_type=c["contract_type"],
        base_salary_monthly=Decimal(str(c.get("base_salary_monthly", 0))),
        base_hourly_rate=Decimal(str(c.get("base_hourly_rate", 0))),
        monthly_hours_standard=Decimal(str(c.get("monthly_hours_standard", 0))),
        commute_allowance_monthly=Decimal(str(c.get("commute_allowance_monthly", 0))),
        head_allowance_monthly=Decimal(str(c.get("head_allowance_monthly", 0))),
        qualification_allowance_monthly=Decimal(
            str(c.get("qualification_allowance_monthly", 0))
        ),
        overnight_per_stay=Decimal(str(c.get("overnight_per_stay", 3000))),
    )


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can run payroll")

    body = parse_body(event)
    period = body.get("period")
    if not period or not _PERIOD_RE.match(period):
        raise HttpError(400, "period must be YYYY-MM")
    target_staff_ids: list[str] | None = body.get("staff_ids")

    period_start, period_end = _period_bounds(period)

    # 指導員一覧
    staff_res = table("STAFF_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    staff_list = [
        s for s in staff_res.get("Items", []) if s.get("status") == "ACTIVE"
    ]
    if target_staff_ids:
        ids = set(target_staff_ids)
        staff_list = [s for s in staff_list if s["staff_id"] in ids]

    runs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for s in staff_list:
        sid = s["staff_id"]
        sk = f"{caller.org_id}#{sid}"

        # 契約取得
        c_res = table("CONTRACTS_TABLE").query(
            KeyConditionExpression=Key("org_staff").eq(sk),
        )
        contract_row = _pick_contract(c_res.get("Items", []), period_start)
        if not contract_row:
            skipped.append({"staff_id": sid, "reason": "no active contract"})
            continue
        contract = _contract_from_row(contract_row)

        # 勤怠取得(entry_id プレフィックスで月内に絞り込み)
        t_res = table("TIME_ENTRIES_TABLE").query(
            KeyConditionExpression=Key("org_staff").eq(sk)
            & Key("entry_id").between(period_start, period_end + "#~"),
        )
        agg = _agg_from_entries(t_res.get("Items", []))
        result = compute_payroll(contract, agg, period)

        run: dict[str, Any] = {
            "org_staff": sk,
            "period": period,
            "org_id": caller.org_id,
            "staff_id": sid,
            "org_period": f"{caller.org_id}#{period}",
            "status": "DRAFT",
            "contract_type": contract.contract_type,
            "hours_regular": agg.hours_regular,
            "hours_overtime": agg.hours_overtime,
            "hours_late_night": agg.hours_late_night,
            "hours_holiday": agg.hours_holiday,
            "hours_training": agg.hours_training,
            "overnight_stays": agg.overnight_stays,
            "base_pay": result.base_pay,
            "overtime_pay": result.overtime_pay,
            "late_night_pay": result.late_night_pay,
            "holiday_pay": result.holiday_pay,
            "training_pay": result.training_pay,
            "overnight_pay": result.overnight_pay,
            "commute_allowance": result.commute_allowance,
            "head_allowance": result.head_allowance,
            "qualification_allowance": result.qualification_allowance,
            "gross_pay": result.gross_pay,
            "notes": result.notes,
            "calculated_at": iso_now(),
            "calculated_by": caller.user_id,
        }
        table("PAYROLL_RUNS_TABLE").put_item(Item=run)
        write_audit_log("payroll_run", f"{sid}#{period}", "calculate", caller, after=run)
        runs.append(run)

    return response(
        200,
        {
            "period": period,
            "calculated": len(runs),
            "skipped": skipped,
            "runs": runs,
        },
    )


handler = handler_wrapper(_impl)

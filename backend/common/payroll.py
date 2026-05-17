"""給与計算ユーティリティ(spec.md §6 / ひまわり賃金規程 別表1 をベース)。

簡略化方針(MVP):
- 正規(REGULAR): 月給制。time_entries から hours_overtime/holiday/late_night/training を集計し、
  時給換算で各割増を加算。さらに通勤手当・主任手当・資格手当などを加える。
- パート(PART_TIME): 時給制。hours_regular + 各種割増 + 通勤実費。

割増率(ひまわり別表1):
- regular(所定): 100%
- overtime(法定外、深夜外): 125%
- overtime かつ深夜(22-5時): 150%
- 月60h超(法定外): 150%(深夜は175%)
- holiday(法定休日): 135% (深夜は160%)

正規の所定労働時間(月平均): 別表1 ※ より
  (年日数 - 休日数) × 5時間 ÷ 12 で算出 -> ここでは 入力 monthly_hours で受け取る
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _D(x: Any) -> Decimal:
    return Decimal(str(x))


def _round_yen(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@dataclass
class Contract:
    contract_type: str  # REGULAR | PART_TIME
    base_salary_monthly: Decimal = Decimal("0")  # REGULAR の月給
    base_hourly_rate: Decimal = Decimal("0")  # PART_TIME の時給
    monthly_hours_standard: Decimal = Decimal("0")  # REGULAR の月平均所定労働時間(時給換算用)
    commute_allowance_monthly: Decimal = Decimal("0")
    head_allowance_monthly: Decimal = Decimal("0")  # 主任(副主任)手当
    qualification_allowance_monthly: Decimal = Decimal("0")  # 資格手当
    overtime_rate: Decimal = Decimal("1.25")
    late_night_rate: Decimal = Decimal("1.50")
    holiday_rate: Decimal = Decimal("1.35")
    overnight_per_stay: Decimal = Decimal("3000")  # キャンプ等の宿泊手当(別表1 ¥3,000/泊)


@dataclass
class TimeAggregate:
    hours_regular: Decimal = Decimal("0")
    hours_overtime: Decimal = Decimal("0")
    hours_late_night: Decimal = Decimal("0")  # 深夜帯(22-5)の時間
    hours_holiday: Decimal = Decimal("0")
    hours_training: Decimal = Decimal("0")  # 研修時間(時間外として算出)
    overnight_stays: int = 0


@dataclass
class PayrollResult:
    period: str
    base_pay: Decimal = Decimal("0")
    overtime_pay: Decimal = Decimal("0")
    late_night_pay: Decimal = Decimal("0")
    holiday_pay: Decimal = Decimal("0")
    training_pay: Decimal = Decimal("0")
    overnight_pay: Decimal = Decimal("0")
    commute_allowance: Decimal = Decimal("0")
    head_allowance: Decimal = Decimal("0")
    qualification_allowance: Decimal = Decimal("0")
    gross_pay: Decimal = Decimal("0")
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


def compute_bonus(
    contract: Contract,
    season: str,  # SUMMER | WINTER
    rate_months: Decimal,
) -> Decimal:
    """賞与額(円)を算出。

    ひまわり別表1: 夏季・冬季とも 2.0ヶ月分。基準日に在籍する正規指導員のみ対象、
    パートは別表で「勤務状況等を考慮し寸志を支給することがある」とされ
    自動算出対象外(ゼロ)。
    """
    if contract.contract_type != "REGULAR":
        return Decimal("0")
    return _round_yen(contract.base_salary_monthly * rate_months)


def compute_payroll(
    contract: Contract, agg: TimeAggregate, period: str
) -> PayrollResult:
    """1人分の月次給与を計算。控除(社保等)は本MVPでは対象外。"""
    out = PayrollResult(period=period)

    if contract.contract_type == "REGULAR":
        if contract.monthly_hours_standard <= 0:
            out.notes.append("monthly_hours_standard=0 のため時間外計算は0扱い")
            hourly = Decimal("0")
        else:
            hourly = (
                contract.base_salary_monthly / contract.monthly_hours_standard
            ).quantize(Decimal("0.01"))
        out.base_pay = contract.base_salary_monthly
    elif contract.contract_type == "PART_TIME":
        hourly = contract.base_hourly_rate
        out.base_pay = _round_yen(hourly * agg.hours_regular)
    else:
        raise ValueError(f"unknown contract_type: {contract.contract_type}")

    out.overtime_pay = _round_yen(hourly * contract.overtime_rate * agg.hours_overtime)
    out.late_night_pay = _round_yen(
        hourly * contract.late_night_rate * agg.hours_late_night
    )
    out.holiday_pay = _round_yen(hourly * contract.holiday_rate * agg.hours_holiday)
    # 研修時間は時間外として算定(別表1)
    out.training_pay = _round_yen(
        hourly * contract.overtime_rate * agg.hours_training
    )
    out.overnight_pay = contract.overnight_per_stay * _D(agg.overnight_stays)
    out.commute_allowance = contract.commute_allowance_monthly
    out.head_allowance = contract.head_allowance_monthly
    out.qualification_allowance = contract.qualification_allowance_monthly

    out.gross_pay = (
        out.base_pay
        + out.overtime_pay
        + out.late_night_pay
        + out.holiday_pay
        + out.training_pay
        + out.overnight_pay
        + out.commute_allowance
        + out.head_allowance
        + out.qualification_allowance
    )
    return out

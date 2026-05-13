"""給与計算のユニットテスト。

実行: cd backend && python -m unittest tests.test_payroll
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from common.payroll import Contract, TimeAggregate, compute_payroll


class PayrollTest(unittest.TestCase):
    def test_part_time_basic(self):
        """時給1150、所定20時間 → ¥23,000(時給×所定のみ)"""
        c = Contract(
            contract_type="PART_TIME",
            base_hourly_rate=Decimal("1150"),
        )
        agg = TimeAggregate(hours_regular=Decimal("20"))
        r = compute_payroll(c, agg, "2026-05")
        self.assertEqual(r.base_pay, Decimal("23000"))
        self.assertEqual(r.gross_pay, Decimal("23000"))

    def test_part_time_overtime_125(self):
        """時給1000、時間外2時間 → 2 * 1000 * 1.25 = 2500"""
        c = Contract(
            contract_type="PART_TIME",
            base_hourly_rate=Decimal("1000"),
        )
        agg = TimeAggregate(hours_regular=Decimal("8"), hours_overtime=Decimal("2"))
        r = compute_payroll(c, agg, "2026-05")
        self.assertEqual(r.base_pay, Decimal("8000"))
        self.assertEqual(r.overtime_pay, Decimal("2500"))
        self.assertEqual(r.gross_pay, Decimal("10500"))

    def test_regular_with_allowances_and_overnight(self):
        """正規:月給130000、所定100h、時間外5h、キャンプ宿泊1回、通勤4100、主任10000、資格5000"""
        c = Contract(
            contract_type="REGULAR",
            base_salary_monthly=Decimal("130000"),
            monthly_hours_standard=Decimal("100"),
            commute_allowance_monthly=Decimal("4100"),
            head_allowance_monthly=Decimal("10000"),
            qualification_allowance_monthly=Decimal("5000"),
        )
        agg = TimeAggregate(hours_overtime=Decimal("5"), overnight_stays=1)
        r = compute_payroll(c, agg, "2026-05")
        # 時給 = 130000/100 = 1300、時間外 = 1300*1.25*5 = 8125
        self.assertEqual(r.base_pay, Decimal("130000"))
        self.assertEqual(r.overtime_pay, Decimal("8125"))
        self.assertEqual(r.overnight_pay, Decimal("3000"))
        self.assertEqual(r.commute_allowance, Decimal("4100"))
        self.assertEqual(r.head_allowance, Decimal("10000"))
        self.assertEqual(r.qualification_allowance, Decimal("5000"))
        # 合計 = 130000 + 8125 + 3000 + 4100 + 10000 + 5000 = 160225
        self.assertEqual(r.gross_pay, Decimal("160225"))

    def test_holiday_rate_135(self):
        c = Contract(
            contract_type="PART_TIME",
            base_hourly_rate=Decimal("1000"),
        )
        agg = TimeAggregate(hours_holiday=Decimal("4"))
        r = compute_payroll(c, agg, "2026-05")
        self.assertEqual(r.holiday_pay, Decimal("5400"))

    def test_late_night_rate_150(self):
        c = Contract(
            contract_type="PART_TIME",
            base_hourly_rate=Decimal("1000"),
        )
        agg = TimeAggregate(hours_late_night=Decimal("2"))
        r = compute_payroll(c, agg, "2026-05")
        self.assertEqual(r.late_night_pay, Decimal("3000"))

    def test_training_treated_as_overtime(self):
        c = Contract(
            contract_type="PART_TIME",
            base_hourly_rate=Decimal("1000"),
        )
        agg = TimeAggregate(hours_training=Decimal("3"))
        r = compute_payroll(c, agg, "2026-05")
        self.assertEqual(r.training_pay, Decimal("3750"))

    def test_regular_with_zero_monthly_hours_note(self):
        c = Contract(
            contract_type="REGULAR",
            base_salary_monthly=Decimal("130000"),
            monthly_hours_standard=Decimal("0"),
        )
        agg = TimeAggregate(hours_overtime=Decimal("5"))
        r = compute_payroll(c, agg, "2026-05")
        self.assertEqual(r.overtime_pay, Decimal("0"))
        self.assertIn("monthly_hours_standard=0", r.notes[0])

    def test_invalid_contract_type_raises(self):
        c = Contract(contract_type="UNKNOWN")
        with self.assertRaises(ValueError):
            compute_payroll(c, TimeAggregate(), "2026-05")


if __name__ == "__main__":
    unittest.main()

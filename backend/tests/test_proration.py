"""按分計算のユニットテスト(spec.md §5.5)。

実行: cd backend && python -m unittest tests.test_proration
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from common.proration import prorate


class ProrationTest(unittest.TestCase):
    def test_sum_matches_actual(self):
        """配分合計は actual_total と完全一致する(全ケース共通の不変)。"""
        cases = [
            ([5000, 3000, 1500], 8500),
            ([5000, 3000, 1500], 10500),
            ([1, 1, 1], 100),
            ([100, 100, 100], 0),
            ([1000, 1000], 1),
        ]
        for planned, actual in cases:
            with self.subTest(planned=planned, actual=actual):
                out = prorate(planned, actual)
                self.assertEqual(sum(out, Decimal("0")), Decimal(actual))

    def test_surplus_refund_camp(self):
        """spec.md §3.5 の典型例:
        planned [5000, 3000, 1500] = 9500、実費 8500 → 1000 余剰。
        比例配分でほぼ planned×(8500/9500)、端数を最大負担者に。"""
        out = prorate([5000, 3000, 1500], 8500)
        # 8500/9500 ≈ 0.8947
        # 5000 -> 4473.68 -> 4473 + 1 (端数最大負担者)= 4474
        # 3000 -> 2684.21 -> 2684
        # 1500 -> 1342.10 -> 1342
        self.assertEqual(out, [Decimal(4474), Decimal(2684), Decimal(1342)])
        self.assertEqual(sum(out, Decimal("0")), Decimal(8500))

    def test_shortage_extra_charge(self):
        """実費が見込みを上回る(追加徴収)ケース。"""
        out = prorate([5000, 3000, 1500], 10500)  # 見込9500 → 不足1000
        self.assertEqual(sum(out, Decimal("0")), Decimal(10500))
        # 最大負担者(5000)が最も多くを負担する
        self.assertGreater(out[0], out[1])
        self.assertGreater(out[1], out[2])

    def test_equal_split_when_planned_all_zero(self):
        """planned が全員0なら均等割り(残差は先頭から+1ずつ)。"""
        self.assertEqual(prorate([0, 0, 0], 100), [Decimal(34), Decimal(33), Decimal(33)])
        self.assertEqual(prorate([0, 0, 0], 0), [Decimal(0), Decimal(0), Decimal(0)])

    def test_single_participant(self):
        self.assertEqual(prorate([5000], 4321), [Decimal(4321)])

    def test_no_participants(self):
        self.assertEqual(prorate([], 0), [])

    def test_zero_actual(self):
        """実費0(全額返金)→ 全員0が配分される(差額が個別計算側でREFUNDになる)。"""
        out = prorate([5000, 3000, 1500], 0)
        self.assertEqual(out, [Decimal(0), Decimal(0), Decimal(0)])

    def test_max_payer_breaks_tie_by_index(self):
        """planned 同値時は先頭インデックスから端数を割り当てる(決定的)。"""
        # planned合計300, actual 100 -> 100/3 = 33.33 → 各33、残1を先頭へ
        out = prorate([100, 100, 100], 100)
        self.assertEqual(out, [Decimal(34), Decimal(33), Decimal(33)])

    def test_negative_remainder_when_planned_lt_actual_split(self):
        """切り捨てで余る残差は負にならない(切り捨ては必ず target 以下)。
        ただし planned 全0 の均等割で actual<0 を入れたら負になるが、想定外。"""
        out = prorate([1, 2, 3], 6)
        self.assertEqual(sum(out, Decimal("0")), Decimal(6))


if __name__ == "__main__":
    unittest.main()

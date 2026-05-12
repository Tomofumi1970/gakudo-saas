"""按分計算ユーティリティ(spec.md §5.5)。

イベント実費精算:
- 各参加者の見込み負担額(planned_charge)に比例して実費を配分
- 端数は合計が一致するよう「最大負担者から±1円ずつ」調整(明示的ルール)
- planned_charge が全員0、または合計が0の場合は均等割り
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable


def prorate(
    planned_charges: Iterable[Decimal | int | str],
    actual_total: Decimal | int | str,
) -> list[Decimal]:
    """planned_charges の比率で actual_total を配分し、合計が完全一致するよう端数調整。

    Args:
        planned_charges: 各参加者の見込み負担額(順序保持)
        actual_total: 配分対象の実費総額(整数円相当)

    Returns:
        各参加者の実費按分額(入力と同順、整数円のDecimal)。
        合計は actual_total と必ず一致する。
    """
    planned = [Decimal(str(p)) for p in planned_charges]
    target = Decimal(str(actual_total)).quantize(Decimal("1"))
    n = len(planned)
    if n == 0:
        return []

    total_planned = sum(planned, Decimal("0"))

    if total_planned <= 0:
        # 均等割り(planned全員0など)
        base = (target // n)
        out = [base for _ in range(n)]
        remainder = target - base * n
        # 余りは先頭から+1ずつ(planned同値だが安定したルール)
        i = 0
        step = Decimal("1") if remainder >= 0 else Decimal("-1")
        remaining = abs(int(remainder))
        while remaining > 0:
            out[i] += step
            i = (i + 1) % n
            remaining -= 1
        return out

    # 比例配分(端数切り捨て)
    raw = [(p * target / total_planned) for p in planned]
    out = [r.quantize(Decimal("1"), rounding="ROUND_DOWN") for r in raw]
    remainder = target - sum(out, Decimal("0"))

    # 端数を最大負担者(planned降順、同値なら先頭)から±1円ずつ
    order = sorted(range(n), key=lambda i: (-planned[i], i))
    step = Decimal("1") if remainder >= 0 else Decimal("-1")
    remaining = abs(int(remainder))
    k = 0
    while remaining > 0:
        out[order[k % n]] += step
        k += 1
        remaining -= 1

    return out

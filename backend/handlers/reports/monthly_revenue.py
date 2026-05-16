"""GET /reports/monthly-revenue?period=YYYY-MM — 月次売上レポート。

集計対象: Invoices テーブルから org_billing_unit="<org_id>#MONTH#<period>" 等の
請求書を集計する。MONTH のみでなく、当該月内に発行された EVENT/VACATION/OUTING も
含めるかは「period の含まれる文字列」で前方一致(billing_unit_prefix)するクエリで決める。

クエリ:
  period (YYYY-MM)            必須
  include_other_units (bool)  任意(true なら同月の EVENT 等も含める)
"""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    query_param,
    response,
    table,
)

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _scan_invoices(caller: Caller) -> list[dict[str, Any]]:
    """テナント内全請求書を scan(規模100世帯前提)。

    GSI gsi1-orgbilling-status は (org_billing_unit, status) で組まれており、
    特定 billing_unit の集計には使えるが、汎用集計には scan が手軽。
    """
    last_key = None
    items: list[dict[str, Any]] = []
    while True:
        kwargs: dict[str, Any] = {
            "FilterExpression": Key("org_id").eq(caller.org_id),
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        res = table("INVOICES_TABLE").scan(**kwargs)
        items.extend(res.get("Items", []))
        last_key = res.get("LastEvaluatedKey")
        if not last_key:
            break
    return items


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can view reports")

    period = query_param(event, "period")
    if not period or not _PERIOD_RE.match(period):
        raise HttpError(400, "period must be YYYY-MM")
    include_other = (query_param(event, "include_other_units") == "true")

    invoices = _scan_invoices(caller)

    # 同月の MONTH#period に限定、もしくは include_other なら同月内の他単位も
    def matches(bu: str) -> bool:
        if bu == f"MONTH#{period}":
            return True
        if include_other and period in bu:
            # 例: EVENT には日付が含まれない場合があるので、generated_at で別途絞るのが本来は厳密
            return True
        return False

    target = [i for i in invoices if matches(i.get("billing_unit", ""))]

    total = sum((Decimal(str(i.get("total", 0))) for i in target), Decimal("0"))
    paid = sum(
        (Decimal(str(i.get("total", 0))) for i in target if i.get("status") == "PAID"),
        Decimal("0"),
    )
    unpaid = total - paid

    by_status: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "total": Decimal("0")})
    for i in target:
        s = i.get("status", "UNKNOWN")
        by_status[s]["count"] += 1
        by_status[s]["total"] += Decimal(str(i.get("total", 0)))

    return response(
        200,
        {
            "period": period,
            "invoice_count": len(target),
            "total_billed": total,
            "total_paid": paid,
            "total_unpaid": unpaid,
            "by_status": {k: v for k, v in by_status.items()},
        },
    )


handler = handler_wrapper(_impl)

"""GET /reports/unpaid — 未収一覧(status != PAID の請求書)。"""
from __future__ import annotations

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


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can view reports")

    items: list[dict[str, Any]] = []
    last_key = None
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

    only_issued = query_param(event, "only_issued") == "true"
    unpaid = [i for i in items if i.get("status") != "PAID"]
    if only_issued:
        unpaid = [i for i in unpaid if i.get("status") == "ISSUED"]

    # 世帯別合算
    from collections import defaultdict
    by_household: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"household_id": "", "count": 0, "total": Decimal("0"), "items": []}
    )
    for inv in unpaid:
        hid = inv.get("household_id", "")
        b = by_household[hid]
        b["household_id"] = hid
        b["count"] += 1
        b["total"] += Decimal(str(inv.get("total", 0)))
        b["items"].append(
            {
                "billing_unit": inv.get("billing_unit"),
                "status": inv.get("status"),
                "total": Decimal(str(inv.get("total", 0))),
            }
        )

    total_unpaid = sum((b["total"] for b in by_household.values()), Decimal("0"))
    return response(
        200,
        {
            "invoice_count": len(unpaid),
            "household_count": len(by_household),
            "total_unpaid": total_unpaid,
            "by_household": list(by_household.values()),
        },
    )


handler = handler_wrapper(_impl)

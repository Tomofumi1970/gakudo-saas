"""GET /households/{household_id}/invoices — 世帯の請求書一覧。

クエリ:
  billing_unit_prefix (str) 任意(例: "MONTH#2026" で2026年の月次のみ絞り込み)
"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    path_param,
    query_param,
    response,
    table,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    household_id = path_param(event, "household_id")

    # 世帯の存在確認
    house = table("HOUSEHOLDS_TABLE").get_item(
        Key={"org_id": caller.org_id, "household_id": household_id}
    )
    if "Item" not in house:
        raise HttpError(404, "household not found")

    pk = f"{caller.org_id}#{household_id}"
    prefix = query_param(event, "billing_unit_prefix")

    cond = Key("org_household").eq(pk)
    if prefix:
        cond = cond & Key("billing_unit").begins_with(prefix)

    res = table("INVOICES_TABLE").query(KeyConditionExpression=cond)
    items = res.get("Items", [])
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

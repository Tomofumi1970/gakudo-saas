"""GET /catalog/items — 自施設の料金品目一覧。"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import Caller, handler_wrapper, query_param, response, table


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    res = table("ITEM_CATALOG_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    items = res.get("Items", [])

    only_active = query_param(event, "active") == "true"
    if only_active:
        items = [i for i in items if i.get("active", True)]

    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

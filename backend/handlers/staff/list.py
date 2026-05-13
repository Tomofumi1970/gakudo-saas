"""GET /staff — 自施設の指導員一覧。"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import Caller, handler_wrapper, query_param, response, table


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    res = table("STAFF_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    items = res.get("Items", [])
    active_only = query_param(event, "active") == "true"
    if active_only:
        items = [s for s in items if s.get("status") == "ACTIVE"]
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

"""GET /resolutions — 議案一覧。"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import Caller, handler_wrapper, query_param, response, table


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    res = table("RESOLUTIONS_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    items = res.get("Items", [])
    assembly = query_param(event, "assembly_id")
    if assembly:
        items = [r for r in items if r.get("assembly_id") == assembly]
    items.sort(key=lambda r: (r.get("assembly_id", ""), r.get("order_no", "")))
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

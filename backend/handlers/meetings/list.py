"""GET /meetings — 議事録一覧(スタッフ用、DRAFT含む)。"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import Caller, handler_wrapper, query_param, response, table


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    res = table("MEETING_MINUTES_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    items = res.get("Items", [])
    mtype = query_param(event, "type")
    if mtype:
        items = [m for m in items if m.get("meeting_type") == mtype]
    items.sort(key=lambda m: m.get("meeting_date", ""), reverse=True)
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

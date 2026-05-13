"""GET /me/meetings — 保護者向け、PUBLISHED の議事録一覧。"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import Caller, handler_wrapper, response, table


def _impl(_event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    res = table("MEETING_MINUTES_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    items = [m for m in res.get("Items", []) if m.get("status") == "PUBLISHED"]
    items.sort(key=lambda m: m.get("meeting_date", ""), reverse=True)
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

"""GET /households — 自施設の世帯一覧を返す(マルチテナント分離)。"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import Caller, handler_wrapper, response, table


def _impl(_event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    res = table("HOUSEHOLDS_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    items = res.get("Items", [])
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

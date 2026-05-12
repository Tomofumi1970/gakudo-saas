"""GET /households/{household_id}/members — 世帯のメンバー一覧。

GSI1 (household_id + member_type) を使って取得。
"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    path_param,
    response,
    table,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    household_id = path_param(event, "household_id")

    # 世帯の存在確認(テナント分離)
    house = table("HOUSEHOLDS_TABLE").get_item(
        Key={"org_id": caller.org_id, "household_id": household_id}
    )
    if "Item" not in house:
        raise HttpError(404, "household not found")

    res = table("MEMBERS_TABLE").query(
        IndexName="gsi1-household-type",
        KeyConditionExpression=Key("household_id").eq(household_id),
    )
    # テナント間漏洩防止のため org_id で再フィルタ
    items = [m for m in res.get("Items", []) if m.get("org_id") == caller.org_id]
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

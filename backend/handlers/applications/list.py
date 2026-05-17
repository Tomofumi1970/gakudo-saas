"""GET /applications — 入所申込一覧(スタッフ用)。"""
from __future__ import annotations

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
        raise HttpError(403, "only staff can view applications")
    res = table("APPLICATIONS_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    items = res.get("Items", [])
    status = query_param(event, "status")
    if status:
        items = [a for a in items if a.get("status") == status]
    items.sort(key=lambda a: a.get("submitted_at", ""), reverse=True)
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

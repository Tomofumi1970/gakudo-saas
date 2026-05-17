"""GET /shifts?date=YYYY-MM-DD — 指定日のシフト一覧。"""
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
    date = query_param(event, "date")
    if not date:
        raise HttpError(400, "date query parameter is required")
    pk = f"{caller.org_id}#{date}"
    res = table("SHIFTS_TABLE").query(
        KeyConditionExpression=Key("org_date").eq(pk),
    )
    items = res.get("Items", [])
    return response(200, {"date": date, "items": items, "count": len(items)})


handler = handler_wrapper(_impl)

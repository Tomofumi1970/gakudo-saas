"""GET /members/{member_id}/attendance?from=YYYY-MM-DD&to=YYYY-MM-DD — 個人の出席履歴。"""
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
    member_id = path_param(event, "member_id")
    pk = f"{caller.org_id}#{member_id}"
    cond = Key("org_member").eq(pk)
    date_from = query_param(event, "from")
    date_to = query_param(event, "to")
    if date_from and date_to:
        cond = cond & Key("work_date").between(date_from, date_to)
    elif date_from:
        cond = cond & Key("work_date").gte(date_from)
    elif date_to:
        cond = cond & Key("work_date").lte(date_to)

    res = table("ATTENDANCE_TABLE").query(
        IndexName="gsi1-orgmember-date",
        KeyConditionExpression=cond,
    )
    items = res.get("Items", [])
    return response(200, {"member_id": member_id, "items": items, "count": len(items)})


handler = handler_wrapper(_impl)

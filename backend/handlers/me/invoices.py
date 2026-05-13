"""GET /me/invoices — 自世帯の請求書一覧(保護者向け)。"""
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
    if not caller.household_id:
        raise HttpError(400, "no household associated with this user")

    pk = f"{caller.org_id}#{caller.household_id}"
    prefix = query_param(event, "billing_unit_prefix")
    cond = Key("org_household").eq(pk)
    if prefix:
        cond = cond & Key("billing_unit").begins_with(prefix)
    res = table("INVOICES_TABLE").query(KeyConditionExpression=cond)
    items = res.get("Items", [])
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

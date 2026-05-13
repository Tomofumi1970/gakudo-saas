"""GET /documents — 規程文書一覧。

クエリ:
  doc_key     任意(指定があれば全バージョン、なければ全 doc_key の ACTIVE のみ)
  status      任意(ACTIVE | SUPERSEDED)
"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    handler_wrapper,
    query_param,
    response,
    table,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    doc_key = query_param(event, "doc_key")
    status_filter = query_param(event, "status")
    docs = table("DOCUMENTS_TABLE")

    items: list[dict[str, Any]] = []
    if doc_key:
        pk = f"{caller.org_id}#{doc_key}"
        res = docs.query(KeyConditionExpression=Key("org_doc_key").eq(pk))
        items = res.get("Items", [])
    else:
        # 全 ACTIVE を scan(規模100施設×数十文書なら許容)
        res = docs.scan(
            FilterExpression=Key("org_id").eq(caller.org_id)
            & Key("status").eq("ACTIVE"),
        )
        items = res.get("Items", [])

    if status_filter:
        items = [d for d in items if d.get("status") == status_filter]

    items.sort(key=lambda d: (d.get("doc_key", ""), d.get("version", "")), reverse=True)
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

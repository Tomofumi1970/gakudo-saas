"""GET /reports/enrollment — 在籍児童のスナップショット集計。

簡易版: 現時点で各ステータス区分の人数を集計。
spec.md §10 未解決の論点として「期間内の月別推移」は将来 Phase。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    response,
    table,
)


def _impl(_event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can view reports")

    items: list[dict[str, Any]] = []
    last_key = None
    while True:
        kwargs: dict[str, Any] = {
            "FilterExpression": Key("org_id").eq(caller.org_id),
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        res = table("MEMBERS_TABLE").scan(**kwargs)
        items.extend(res.get("Items", []))
        last_key = res.get("LastEvaluatedKey")
        if not last_key:
            break

    by_status = Counter(m.get("status", "") for m in items)
    by_type = Counter(m.get("member_type", "") for m in items)

    # 在籍中(ACTIVE児童)の学年分布
    active_children = [
        m for m in items if m.get("status") == "ACTIVE" and m.get("member_type") == "child"
    ]
    by_grade = Counter(m.get("grade", "-") for m in active_children)

    return response(
        200,
        {
            "total_members": len(items),
            "by_status": dict(by_status),
            "by_member_type": dict(by_type),
            "active_children": {
                "count": len(active_children),
                "by_grade": dict(sorted(by_grade.items())),
            },
        },
    )


handler = handler_wrapper(_impl)

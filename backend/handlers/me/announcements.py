"""GET /me/announcements — 自分宛のお知らせ一覧(SENT のみ)。

MVP では「自施設のSENTお知らせを新しい順に返す」のみ実装。
将来は target_audience/HIGH_GRADE 等で世帯属性に合うものに絞り込む。
"""
from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import Caller, handler_wrapper, response, table


def _impl(_event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    res = table("ANNOUNCEMENTS_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    items = [a for a in res.get("Items", []) if a.get("status") == "SENT"]
    items.sort(key=lambda a: a.get("sent_at", ""), reverse=True)
    return response(200, {"items": items, "count": len(items)})


handler = handler_wrapper(_impl)

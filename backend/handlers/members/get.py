"""GET /members/{member_id} — 単一メンバー取得。"""
from __future__ import annotations

from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    path_param,
    response,
    table,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    member_id = path_param(event, "member_id")
    res = table("MEMBERS_TABLE").get_item(
        Key={"org_id": caller.org_id, "member_id": member_id}
    )
    if "Item" not in res:
        raise HttpError(404, "member not found")
    m = res["Item"]
    # 保護者は自世帯メンバーのみ閲覧可
    if caller.user_type == "parent" and caller.household_id != m.get("household_id"):
        raise HttpError(403, "not allowed")
    return response(200, m)


handler = handler_wrapper(_impl)

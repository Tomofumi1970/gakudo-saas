"""GET /me/household — 自分の世帯と所属メンバー(保護者向け)。

custom:household_id クレームから自世帯を特定。staff の場合は household_id 無しなら 400。
"""
from __future__ import annotations

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
    if not caller.household_id:
        raise HttpError(400, "no household associated with this user")

    house = table("HOUSEHOLDS_TABLE").get_item(
        Key={"org_id": caller.org_id, "household_id": caller.household_id}
    )
    if "Item" not in house:
        raise HttpError(404, "household not found")

    members = table("MEMBERS_TABLE").query(
        IndexName="gsi1-household-type",
        KeyConditionExpression=Key("household_id").eq(caller.household_id),
    )
    member_items = [
        m for m in members.get("Items", []) if m.get("org_id") == caller.org_id
    ]

    return response(200, {"household": house["Item"], "members": member_items})


handler = handler_wrapper(_impl)

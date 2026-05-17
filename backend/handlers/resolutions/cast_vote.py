"""POST /resolutions/{resolution_id}/votes — 議決権を行使。

保護者(user_type=parent)が世帯単位で1票。同世帯の再投票は上書き。
委任の場合は choice="proxy" + proxy_to(委任先 household_id)を指定。

Body:
  choice (str)   必須(options のいずれか or "proxy")
  proxy_to (str) choice="proxy" のとき必須
"""
from __future__ import annotations

from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    parse_body,
    path_param,
    response,
    table,
    write_audit_log,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if not caller.household_id:
        raise HttpError(403, "voter must be associated with a household")

    resolution_id = path_param(event, "resolution_id")
    body = parse_body(event)
    choice = body.get("choice")
    if not choice:
        raise HttpError(400, "choice is required")

    res = table("RESOLUTIONS_TABLE").get_item(
        Key={"org_id": caller.org_id, "resolution_id": resolution_id}
    )
    if "Item" not in res:
        raise HttpError(404, "resolution not found")
    r = res["Item"]
    if r.get("status") != "OPEN":
        raise HttpError(409, f"resolution is {r.get('status')}")

    if choice != "proxy":
        if choice not in r.get("options", []):
            raise HttpError(400, f"choice must be one of {r.get('options')}")

    pk = f"{caller.org_id}#{resolution_id}"
    now = iso_now()
    item: dict[str, Any] = {
        "org_resolution": pk,
        "household_id": caller.household_id,
        "org_id": caller.org_id,
        "resolution_id": resolution_id,
        "choice": choice,
        "voter_user_id": caller.user_id,
        "voter_email": caller.email or "",
        "voted_at": now,
    }
    if choice == "proxy":
        proxy_to = body.get("proxy_to")
        if not proxy_to:
            raise HttpError(400, "proxy_to is required when choice=proxy")
        item["proxy_to"] = proxy_to

    table("BALLOTS_TABLE").put_item(Item=item)
    write_audit_log(
        "ballot",
        f"{resolution_id}#{caller.household_id}",
        "cast",
        caller,
        after={"choice": choice},
    )
    return response(200, item)


handler = handler_wrapper(_impl)

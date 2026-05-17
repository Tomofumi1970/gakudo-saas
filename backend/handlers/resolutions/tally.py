"""GET /resolutions/{resolution_id}/tally — 議決の集計結果。

委任票は proxy_to の保有票数に加算(2段以上の委任は1段で打ち切る簡易版)。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    path_param,
    response,
    table,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    resolution_id = path_param(event, "resolution_id")
    res = table("RESOLUTIONS_TABLE").get_item(
        Key={"org_id": caller.org_id, "resolution_id": resolution_id}
    )
    if "Item" not in res:
        raise HttpError(404, "resolution not found")
    r = res["Item"]

    pk = f"{caller.org_id}#{resolution_id}"
    ballots_res = table("BALLOTS_TABLE").query(
        KeyConditionExpression=Key("org_resolution").eq(pk),
    )
    ballots = ballots_res.get("Items", [])

    # 委任マップ: proxied_household -> proxy_target_household
    proxy_to: dict[str, str] = {
        b["household_id"]: b["proxy_to"]
        for b in ballots
        if b.get("choice") == "proxy" and b.get("proxy_to")
    }
    direct: dict[str, str] = {
        b["household_id"]: b["choice"]
        for b in ballots
        if b.get("choice") != "proxy"
    }

    # 委任票の解決(1段のみ): proxy先がproxyならabstain扱い
    counts: Counter[str] = Counter()
    weight_by_household: dict[str, int] = defaultdict(int)
    # 直接票はそれぞれ重み1
    for hid, ch in direct.items():
        weight_by_household[hid] += 1
    # 委任元の票を委任先に転送(委任先が直接票を持つ場合のみ転送、それ以外は abstain)
    transferred = 0
    transfers: list[dict[str, str]] = []
    for src, dst in proxy_to.items():
        if dst in direct:
            weight_by_household[dst] += 1
            transferred += 1
            transfers.append({"from": src, "to": dst, "applied": "yes"})
        else:
            counts["abstain"] += 1
            transfers.append({"from": src, "to": dst, "applied": "no_target_vote"})
    for hid, ch in direct.items():
        counts[ch] += weight_by_household[hid]

    total_ballots = len(ballots)
    total_count = sum(counts.values())

    return response(
        200,
        {
            "resolution_id": resolution_id,
            "title": r.get("title"),
            "status": r.get("status"),
            "ballot_count": total_ballots,
            "proxy_count": len(proxy_to),
            "proxy_transferred": transferred,
            "tally": dict(counts),
            "tally_total": total_count,
            "transfers": transfers,
        },
    )


handler = handler_wrapper(_impl)

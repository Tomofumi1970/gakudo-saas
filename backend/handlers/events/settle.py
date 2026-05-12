"""POST /events/{event_id}/settle — イベント実費精算(spec.md §5.5)。

参加者の見込み負担額(planned_charge)に比例して実費総額を按分し、
各参加者の actual_share を Ledger に CHARGE 行として追記する。

Body:
  actual_total (number)  必須(実費総額)
  description (str)      任意(Ledger エントリーの説明)
  include_absent (bool)  任意(true なら attended=false も対象、デフォルトfalse)

処理:
1) 参加者を取得(attended の絞り込み)
2) common.proration.prorate で按分(端数は最大負担者で±1円)
3) 各参加者の actual_share を Ledger に追記(billing_unit = event.billing_unit)
4) Event を status=SETTLED に、actual_total / settled_at を更新
5) 各 EventParticipant に actual_share / ledger_entry_id を保存
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    new_id,
    parse_body,
    path_param,
    response,
    table,
    write_audit_log,
)
from common.proration import prorate


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can settle events")

    event_id = path_param(event, "event_id")
    body = parse_body(event)
    actual_total_raw = body.get("actual_total")
    if actual_total_raw is None:
        raise HttpError(400, "actual_total is required")
    try:
        actual_total = Decimal(str(actual_total_raw))
    except Exception as e:
        raise HttpError(400, f"invalid actual_total: {e}") from e
    include_absent = bool(body.get("include_absent", False))
    description = body.get("description", "イベント実費精算")

    # イベント取得
    ev = table("EVENTS_TABLE").get_item(
        Key={"org_id": caller.org_id, "event_id": event_id}
    )
    if "Item" not in ev:
        raise HttpError(404, "event not found")
    event_row = ev["Item"]
    if event_row.get("status") == "SETTLED":
        raise HttpError(409, "event already settled")

    billing_unit = event_row["billing_unit"]

    # 参加者取得
    pk = f"{caller.org_id}#{event_id}"
    res = table("EVENT_PARTICIPANTS_TABLE").query(
        KeyConditionExpression=Key("org_event").eq(pk),
    )
    all_participants = res.get("Items", [])
    if include_absent:
        targets = list(all_participants)
    else:
        targets = [p for p in all_participants if p.get("attended", True)]
    if not targets:
        raise HttpError(400, "no eligible participants to settle")

    # 按分計算
    planned = [Decimal(str(p["planned_charge"])) for p in targets]
    shares = prorate(planned, actual_total)
    assert sum(shares, Decimal("0")) == actual_total, "proration sum mismatch"

    now = iso_now()
    ledger_table = table("LEDGER_TABLE")
    participants_table = table("EVENT_PARTICIPANTS_TABLE")

    results: list[dict[str, Any]] = []
    for p, share in zip(targets, shares):
        delta = share - Decimal(str(p["planned_charge"]))
        ledger_entry_id = f"{now}#{new_id()[:8]}"
        ledger_item: dict[str, Any] = {
            "org_billing_unit": f"{caller.org_id}#{billing_unit}",
            "ledger_entry_id": ledger_entry_id,
            "org_id": caller.org_id,
            "billing_unit": billing_unit,
            "household_id": p["household_id"],
            "member_id": p["member_id"],
            "item_id": "",  # イベント按分は品目カタログを経由しない
            "item_name": f"{event_row['name']} 実費按分",
            "category": "event_settlement",
            "unit_price": share,
            "quantity": Decimal("1"),
            "amount": share,
            "type": "CHARGE",
            "description": description,
            "event_id": event_id,
            "planned_charge": Decimal(str(p["planned_charge"])),
            "delta_vs_planned": delta,
            "created_at": now,
            "created_by": caller.user_id,
        }
        ledger_table.put_item(Item=ledger_item)

        # 参加者レコード更新
        participants_table.update_item(
            Key={"org_event": pk, "member_id": p["member_id"]},
            UpdateExpression=(
                "SET actual_share = :s, delta_vs_planned = :d, "
                "ledger_entry_id = :l, settled_at = :t"
            ),
            ExpressionAttributeValues={
                ":s": share,
                ":d": delta,
                ":l": ledger_entry_id,
                ":t": now,
            },
        )

        results.append({
            "member_id": p["member_id"],
            "household_id": p["household_id"],
            "planned_charge": Decimal(str(p["planned_charge"])),
            "actual_share": share,
            "delta": delta,
            "ledger_entry_id": ledger_entry_id,
        })

    # イベント更新
    table("EVENTS_TABLE").update_item(
        Key={"org_id": caller.org_id, "event_id": event_id},
        UpdateExpression=(
            "SET #s = :s, actual_total = :a, settled_at = :t, "
            "updated_at = :t, updated_by = :u"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "SETTLED",
            ":a": actual_total,
            ":t": now,
            ":u": caller.user_id,
        },
    )

    write_audit_log(
        "event",
        event_id,
        "settle",
        caller,
        after={"actual_total": actual_total, "participant_count": len(results)},
    )

    return response(200, {
        "event_id": event_id,
        "billing_unit": billing_unit,
        "actual_total": actual_total,
        "participant_count": len(results),
        "results": results,
    })


handler = handler_wrapper(_impl)

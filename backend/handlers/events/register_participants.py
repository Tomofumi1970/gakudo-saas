"""POST /events/{event_id}/participants — 参加者を一括登録。

Body:
  participants (list[dict]) 必須。各要素:
    member_id (str)        必須
    member_name (str)      任意(スナップショット用、省略時はDB引きを試みる)
    household_id (str)     必須(課金の付け先)
    planned_charge (number) 必須(見込み負担額、按分の基準)
    age_tier (str)         任意(adult/afterschool/preschool/junior_high)
    attended (bool)        任意(初期は true)

並行する書き込み競合を避けるため、batch_writer で個別に PutItem。
"""
from __future__ import annotations

from decimal import Decimal
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
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can register event participants")

    event_id = path_param(event, "event_id")
    body = parse_body(event)
    raw_participants = body.get("participants") or []
    if not isinstance(raw_participants, list) or not raw_participants:
        raise HttpError(400, "participants must be a non-empty array")

    # イベント存在確認
    ev = table("EVENTS_TABLE").get_item(
        Key={"org_id": caller.org_id, "event_id": event_id}
    )
    if "Item" not in ev:
        raise HttpError(404, "event not found")
    event_row = ev["Item"]

    now = iso_now()
    pk = f"{caller.org_id}#{event_id}"
    written: list[dict[str, Any]] = []
    participants_table = table("EVENT_PARTICIPANTS_TABLE")

    with participants_table.batch_writer() as batch:
        for p in raw_participants:
            member_id = p.get("member_id")
            household_id = p.get("household_id")
            planned_charge = p.get("planned_charge")
            if not member_id or not household_id or planned_charge is None:
                raise HttpError(
                    400,
                    "each participant requires member_id, household_id, planned_charge",
                )
            try:
                planned_dec = Decimal(str(planned_charge))
            except Exception as e:
                raise HttpError(400, f"invalid planned_charge: {e}") from e

            item: dict[str, Any] = {
                "org_event": pk,
                "member_id": member_id,
                "org_id": caller.org_id,
                "event_id": event_id,
                "event_date": event_row["event_date"],
                "household_id": household_id,
                "planned_charge": planned_dec,
                "attended": bool(p.get("attended", True)),
                "created_at": now,
                "created_by": caller.user_id,
            }
            for k in ("member_name", "age_tier"):
                v = p.get(k)
                if v:
                    item[k] = v
            batch.put_item(Item=item)
            written.append(item)

    # ステータスを OPEN に進める
    if event_row.get("status") == "PLANNING":
        table("EVENTS_TABLE").update_item(
            Key={"org_id": caller.org_id, "event_id": event_id},
            UpdateExpression="SET #s = :s, updated_at = :t, updated_by = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "OPEN",
                ":t": now,
                ":u": caller.user_id,
            },
        )

    write_audit_log("event", event_id, "register_participants", caller, after={"count": len(written)})
    return response(201, {"event_id": event_id, "registered": len(written), "items": written})


handler = handler_wrapper(_impl)

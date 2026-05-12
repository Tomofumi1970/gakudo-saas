"""POST /billing/generate — 指定 billing_unit の請求書を世帯ごとに集計生成。

spec.md §5.2 準拠:
- 台帳エントリー(課金/返金/訂正)を世帯×billing_unit で合計
- 結果を Invoices テーブルにスナップショットとして書き込み
- 既存 Invoice があれば status DRAFT のまま上書き(訂正行追加に対応)

Body:
  billing_unit (str)              必須(例: MONTH#2026-05, EVENT#camp001)
  household_ids (str[])           任意(空ならテナント内の課金がある全世帯)
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    parse_body,
    response,
    table,
    write_audit_log,
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can generate invoices")

    body = parse_body(event)
    billing_unit = body.get("billing_unit")
    target_household_ids = body.get("household_ids")
    if not billing_unit:
        raise HttpError(400, "billing_unit is required")

    # 台帳から該当 billing_unit のエントリーを全取得(テナント+billing_unit でパーティション)
    key = f"{caller.org_id}#{billing_unit}"
    entries: list[dict[str, Any]] = []
    last_key = None
    while True:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("org_billing_unit").eq(key),
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        res = table("LEDGER_TABLE").query(**kwargs)
        entries.extend(res.get("Items", []))
        last_key = res.get("LastEvaluatedKey")
        if not last_key:
            break

    # 世帯ごとに集計
    by_household: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in entries:
        hid = e.get("household_id")
        if not hid:
            continue
        if target_household_ids and hid not in target_household_ids:
            continue
        by_household[hid].append(e)

    now = iso_now()
    invoices_written: list[dict[str, Any]] = []
    for hid, lines in by_household.items():
        total = sum((Decimal(str(l["amount"])) for l in lines), Decimal("0"))
        invoice = {
            "org_household": f"{caller.org_id}#{hid}",
            "billing_unit": billing_unit,
            "org_id": caller.org_id,
            "household_id": hid,
            "org_billing_unit": f"{caller.org_id}#{billing_unit}",
            "status": "DRAFT",  # 発行までは DRAFT
            "total": total,
            "line_count": len(lines),
            "line_entry_ids": [l["ledger_entry_id"] for l in lines],
            "generated_at": now,
            "generated_by": caller.user_id,
        }
        table("INVOICES_TABLE").put_item(Item=invoice)
        write_audit_log("invoice", f"{hid}#{billing_unit}", "generate", caller, after=invoice)
        invoices_written.append(invoice)

    return response(
        200,
        {
            "billing_unit": billing_unit,
            "generated_count": len(invoices_written),
            "invoices": invoices_written,
        },
    )


handler = handler_wrapper(_impl)

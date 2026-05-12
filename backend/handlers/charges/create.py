"""POST /charges — 課金/返金/訂正を台帳(Ledger)に1行追記。

spec.md §5.2 準拠:
- 削除修正ではなく訂正行で整合を取る
- 単価変更耐性のため unit_price/amount をスナップショット保存
- billing_unit は "MONTH#2026-05" "EVENT#camp001" "VACATION#summer-2026" "OUTING#2026-08-20" など

Body:
  household_id (str)              必須
  member_id (str)                 任意(児童特有の課金で指定)
  item_id (str)                   必須(品目カタログから引いて単価をスナップ)
  billing_unit (str)              必須(例: MONTH#2026-05)
  quantity (number)               必須
  type (CHARGE|REFUND|CORRECTION) デフォルト CHARGE
  correction_of (str)             任意(CORRECTION時に元エントリーID)
  description (str)               任意
  override_unit_price (number)    任意(イベント等、品目単価と異なる場合)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    new_id,
    parse_body,
    response,
    table,
    write_audit_log,
)

_VALID_TYPES = {"CHARGE", "REFUND", "CORRECTION"}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can post charges")

    body = parse_body(event)
    household_id = body.get("household_id")
    item_id = body.get("item_id")
    billing_unit = body.get("billing_unit")
    quantity_raw = body.get("quantity")
    entry_type = body.get("type", "CHARGE")

    if not household_id:
        raise HttpError(400, "household_id is required")
    if not item_id:
        raise HttpError(400, "item_id is required")
    if not billing_unit:
        raise HttpError(400, "billing_unit is required")
    if quantity_raw is None:
        raise HttpError(400, "quantity is required")
    if entry_type not in _VALID_TYPES:
        raise HttpError(400, f"invalid type: {entry_type}")

    try:
        quantity = Decimal(str(quantity_raw))
    except Exception as e:
        raise HttpError(400, f"invalid quantity: {e}") from e

    # 世帯の存在確認(テナント分離)
    house = table("HOUSEHOLDS_TABLE").get_item(
        Key={"org_id": caller.org_id, "household_id": household_id}
    )
    if "Item" not in house:
        raise HttpError(404, "household not found")

    # 品目を引いて単価をスナップショット
    cat = table("ITEM_CATALOG_TABLE").get_item(
        Key={"org_id": caller.org_id, "item_id": item_id}
    )
    if "Item" not in cat:
        raise HttpError(404, "catalog item not found")
    catalog_item = cat["Item"]

    override_price = body.get("override_unit_price")
    if override_price is not None:
        try:
            unit_price = Decimal(str(override_price))
        except Exception as e:
            raise HttpError(400, f"invalid override_unit_price: {e}") from e
    else:
        unit_price = Decimal(str(catalog_item["unit_price"]))

    sign = Decimal("-1") if entry_type == "REFUND" else Decimal("1")
    amount = (unit_price * quantity * sign).quantize(Decimal("1"))

    now = iso_now()
    ledger_entry_id = f"{now}#{new_id()[:8]}"

    item: dict[str, Any] = {
        # org_id とテナント分離キーを兼ねる
        "org_billing_unit": f"{caller.org_id}#{billing_unit}",
        "ledger_entry_id": ledger_entry_id,
        "org_id": caller.org_id,
        "billing_unit": billing_unit,
        "household_id": household_id,
        "item_id": item_id,
        "item_name": catalog_item["name"],
        "category": catalog_item.get("category", ""),
        "unit_price": unit_price,
        "quantity": quantity,
        "amount": amount,
        "type": entry_type,
        "created_at": now,
        "created_by": caller.user_id,
    }
    for k in ("member_id", "description", "correction_of"):
        v = body.get(k)
        if v:
            item[k] = v

    table("LEDGER_TABLE").put_item(Item=item)
    write_audit_log("ledger_entry", ledger_entry_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

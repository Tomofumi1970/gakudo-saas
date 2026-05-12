"""POST /catalog/items — 料金品目を新規作成。

billing_unit_type: MONTH | EVENT | VACATION | OUTING | ANNUAL | ONETIME
category: 任意の分類(例: tuition, beverage, lunch, event_fee, fee, membership)
age_tier(オプション): adult | afterschool | preschool | junior_high
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

_VALID_BILLING_UNITS = {"MONTH", "EVENT", "VACATION", "OUTING", "ANNUAL", "ONETIME"}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can edit catalog")

    body = parse_body(event)
    name = body.get("name")
    billing_unit_type = body.get("billing_unit_type")
    unit_price = body.get("unit_price")
    category = body.get("category")

    if not name:
        raise HttpError(400, "name is required")
    if billing_unit_type not in _VALID_BILLING_UNITS:
        raise HttpError(400, f"invalid billing_unit_type: {billing_unit_type}")
    if unit_price is None:
        raise HttpError(400, "unit_price is required")
    if not category:
        raise HttpError(400, "category is required")

    try:
        price_dec = Decimal(str(unit_price))
    except Exception as e:
        raise HttpError(400, f"invalid unit_price: {e}") from e

    item_id = new_id()
    now = iso_now()
    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "item_id": item_id,
        "name": name,
        "billing_unit_type": billing_unit_type,
        "category": category,
        "unit_price": price_dec,
        "active": bool(body.get("active", True)),
        "created_at": now,
        "created_by": caller.user_id,
        "updated_at": now,
        "updated_by": caller.user_id,
    }
    for k in ("age_tier", "description", "valid_from", "valid_to"):
        v = body.get(k)
        if v:
            item[k] = v

    table("ITEM_CATALOG_TABLE").put_item(Item=item)
    write_audit_log("catalog_item", item_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

"""PATCH /households/{household_id} — 世帯情報の部分更新。

更新可能: address, phone, note(その他フィールドは別途検討)
更新前後を AuditLog に追記。
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

_UPDATABLE = ("address", "phone", "note")


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can update households")

    household_id = path_param(event, "household_id")
    body = parse_body(event)

    updates = {k: v for k, v in body.items() if k in _UPDATABLE and v is not None}
    if not updates:
        raise HttpError(400, f"no updatable fields. allowed: {list(_UPDATABLE)}")

    # 既存取得(監査ログ before 用)
    before_res = table("HOUSEHOLDS_TABLE").get_item(
        Key={"org_id": caller.org_id, "household_id": household_id}
    )
    if "Item" not in before_res:
        raise HttpError(404, "household not found")
    before = before_res["Item"]

    now = iso_now()
    expr_parts = ["updated_at = :t", "updated_by = :u"]
    values: dict[str, Any] = {":t": now, ":u": caller.user_id}
    names: dict[str, str] = {}
    for i, (k, v) in enumerate(updates.items()):
        # address/phone/note は予約語ではないがエイリアスで安全側に
        nk = f"#k{i}"
        vk = f":v{i}"
        names[nk] = k
        values[vk] = v
        expr_parts.append(f"{nk} = {vk}")
    upd_expr = "SET " + ", ".join(expr_parts)

    res = table("HOUSEHOLDS_TABLE").update_item(
        Key={"org_id": caller.org_id, "household_id": household_id},
        UpdateExpression=upd_expr,
        ExpressionAttributeNames=names if names else None,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    after = res.get("Attributes", {})

    write_audit_log(
        "household", household_id, "update", caller,
        before={k: before.get(k) for k in updates},
        after=updates,
    )
    return response(200, after)


handler = handler_wrapper(_impl)

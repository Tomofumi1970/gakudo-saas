"""POST /resolutions — 議案(=投票対象)作成。

Body:
  assembly_id (str)   必須(総会識別子、例: GA2026)
  order_no (str)      必須(議案の表示順、ゼロ埋め推奨 "01" 等)
  title (str)         必須
  body (str)          任意(議案の本文)
  options (list[str]) 任意(既定: ["yes", "no", "abstain"])
  voting_opens_at     任意(ISO8601、省略時即時)
  voting_closes_at    任意(ISO8601)
"""
from __future__ import annotations

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


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can create resolutions")

    body = parse_body(event)
    assembly_id = body.get("assembly_id")
    order_no = body.get("order_no")
    title = body.get("title")
    if not assembly_id or not order_no or not title:
        raise HttpError(400, "assembly_id / order_no / title are required")

    options = body.get("options") or ["yes", "no", "abstain"]
    if not isinstance(options, list) or not options:
        raise HttpError(400, "options must be a non-empty array")

    resolution_id = f"{assembly_id}#{order_no}#{new_id()[:6]}"
    now = iso_now()
    item: dict[str, Any] = {
        "org_id": caller.org_id,
        "resolution_id": resolution_id,
        "assembly_id": assembly_id,
        "order_no": order_no,
        "title": title,
        "options": options,
        "status": "OPEN",
        "created_at": now,
        "created_by": caller.user_id,
    }
    for k in ("body", "voting_opens_at", "voting_closes_at"):
        v = body.get(k)
        if v:
            item[k] = v

    table("RESOLUTIONS_TABLE").put_item(Item=item)
    write_audit_log("resolution", resolution_id, "create", caller, after=item)
    return response(201, item)


handler = handler_wrapper(_impl)

"""POST /documents — アップロード済ファイルのメタデータを登録。

Body:
  doc_key                 必須
  doc_type                必須(EMPLOYMENT_RULES | WAGE_RULES | OPERATION_RULES | BYLAWS | CONTRACT | OTHER)
  title                   必須
  description             任意
  s3_key                  必須(upload-url で受け取った値)
  version_stamp           必須(upload-url で受け取った値、SK として利用)
  mime_type, file_size    任意(クライアント側で把握していれば)
  effective_from          任意(YYYY-MM-DD)

処理:
- 同 doc_key の既存 ACTIVE 行をすべて SUPERSEDED に変更
- 新規行を ACTIVE で追加
"""
from __future__ import annotations

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

_VALID_DOC_TYPES = {
    "EMPLOYMENT_RULES",
    "WAGE_RULES",
    "OPERATION_RULES",
    "BYLAWS",
    "CONTRACT",
    "OTHER",
}


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can register documents")

    body = parse_body(event)
    doc_key = body.get("doc_key")
    doc_type = body.get("doc_type")
    title = body.get("title")
    s3_key = body.get("s3_key")
    version_stamp = body.get("version_stamp")

    if not doc_key:
        raise HttpError(400, "doc_key is required")
    if doc_type not in _VALID_DOC_TYPES:
        raise HttpError(400, f"invalid doc_type: {doc_type}")
    if not title or not s3_key or not version_stamp:
        raise HttpError(400, "title, s3_key, version_stamp are required")

    pk = f"{caller.org_id}#{doc_key}"
    docs = table("DOCUMENTS_TABLE")

    # 既存 ACTIVE を SUPERSEDED に
    existing = docs.query(KeyConditionExpression=Key("org_doc_key").eq(pk))
    now = iso_now()
    for d in existing.get("Items", []):
        if d.get("status") == "ACTIVE":
            docs.update_item(
                Key={"org_doc_key": pk, "version": d["version"]},
                UpdateExpression=(
                    "SET #s = :s, superseded_at = :t, superseded_by = :u"
                ),
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":s": "SUPERSEDED",
                    ":t": now,
                    ":u": caller.user_id,
                },
            )

    item: dict[str, Any] = {
        "org_doc_key": pk,
        "version": version_stamp,
        "org_id": caller.org_id,
        "doc_key": doc_key,
        "org_doc_type": f"{caller.org_id}#{doc_type}",
        "doc_type": doc_type,
        "title": title,
        "s3_key": s3_key,
        "status": "ACTIVE",
        "created_at": now,
        "created_by": caller.user_id,
    }
    for k in ("description", "mime_type", "file_size", "effective_from"):
        v = body.get(k)
        if v is not None and v != "":
            item[k] = v

    docs.put_item(Item=item)
    write_audit_log(
        "document", f"{doc_key}#{version_stamp}", "register", caller, after=item
    )
    return response(201, item)


handler = handler_wrapper(_impl)

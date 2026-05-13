"""POST /documents/upload-url — アップロード用 presigned URL を発行。

Body:
  doc_key   必須(例: employment_rules, wage_rules, operation_rules)
  filename  必須(例: 就業規則_v3.pdf)
  mime_type 必須

返却:
  upload_url    PUT で本体をアップロードする URL(10分有効)
  s3_key        アップロード先(後で /documents POST で登録する際に使う)
"""
from __future__ import annotations

import os
import re
from typing import Any

import boto3
from botocore.client import Config

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    new_id,
    parse_body,
    response,
)

_s3 = boto3.client(
    "s3",
    region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "virtual"},
    ),
)
_DOC_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can upload documents")

    body = parse_body(event)
    doc_key = body.get("doc_key")
    filename = body.get("filename")
    mime_type = body.get("mime_type")
    if not doc_key or not _DOC_KEY_RE.match(doc_key):
        raise HttpError(400, "doc_key must be lowercase alnum + underscore")
    if not filename or not mime_type:
        raise HttpError(400, "filename and mime_type are required")

    version_stamp = f"{iso_now().replace(':', '').replace('-', '')[:15]}_{new_id()[:6]}"
    s3_key = f"{caller.org_id}/{doc_key}/{version_stamp}/{filename}"
    bucket = os.environ["DOCUMENTS_BUCKET"]

    url = _s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": s3_key,
            "ContentType": mime_type,
        },
        ExpiresIn=600,
    )

    return response(
        200,
        {
            "upload_url": url,
            "s3_key": s3_key,
            "version_stamp": version_stamp,
            "bucket": bucket,
            "expires_in": 600,
        },
    )


handler = handler_wrapper(_impl)

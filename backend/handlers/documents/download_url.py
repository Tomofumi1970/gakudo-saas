"""GET /documents/{doc_key}/download-url — ダウンロード用 presigned URL を発行。

クエリ:
  version  任意(省略時は ACTIVE 最新)
"""
from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.client import Config
from boto3.dynamodb.conditions import Key

from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    path_param,
    query_param,
    response,
    table,
)

_s3 = boto3.client(
    "s3",
    region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "virtual"},
    ),
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    doc_key = path_param(event, "doc_key")
    pk = f"{caller.org_id}#{doc_key}"
    version = query_param(event, "version")

    docs = table("DOCUMENTS_TABLE")
    if version:
        res = docs.get_item(Key={"org_doc_key": pk, "version": version})
        if "Item" not in res:
            raise HttpError(404, "document version not found")
        item = res["Item"]
    else:
        res = docs.query(KeyConditionExpression=Key("org_doc_key").eq(pk))
        actives = [d for d in res.get("Items", []) if d.get("status") == "ACTIVE"]
        if not actives:
            raise HttpError(404, "no active document for doc_key")
        actives.sort(key=lambda d: d.get("version", ""), reverse=True)
        item = actives[0]

    bucket = os.environ["DOCUMENTS_BUCKET"]
    url = _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": item["s3_key"]},
        ExpiresIn=600,
    )
    return response(
        200,
        {
            "doc_key": doc_key,
            "version": item["version"],
            "title": item.get("title"),
            "download_url": url,
            "expires_in": 600,
        },
    )


handler = handler_wrapper(_impl)

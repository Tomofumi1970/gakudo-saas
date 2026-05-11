"""GET /me — 認証ユーザー自身の情報を返す。

Phase 1 の動作確認用。Cognito Authorizer が JWT 検証済みのクレームを
event['requestContext']['authorizer']['claims'] に渡してくる前提。
"""
import json
import os
from typing import Any


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    claims = (
        event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    )
    body = {
        "env": os.environ.get("ENV_NAME"),
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "org_id": claims.get("custom:org_id"),
        "user_type": claims.get("custom:user_type"),
    }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }

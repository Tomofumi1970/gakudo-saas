"""Lambda共通ユーティリティ。

API Gateway + Cognito Authorizer + DynamoDB 構成の Lambda ハンドラで共通利用。
spec.md §3.2 のテナント分離(org_id)と §3.4 の監査ログを必ず通すための足回り。
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ddb = boto3.resource("dynamodb")


def table(env_var: str):
    name = os.environ[env_var]
    return _ddb.Table(name)


@dataclass(frozen=True)
class Caller:
    """Cognito JWT クレームから抽出した呼び出し元の文脈。"""

    user_id: str
    email: str | None
    org_id: str
    user_type: str | None
    household_id: str | None  # 保護者(user_type=parent)のみ


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _claims(event: dict[str, Any]) -> dict[str, Any]:
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
    )


def caller_from_event(event: dict[str, Any]) -> Caller:
    c = _claims(event)
    org_id = c.get("custom:org_id")
    sub = c.get("sub")
    if not org_id or not sub:
        raise HttpError(403, "missing tenant context")
    return Caller(
        user_id=sub,
        email=c.get("email"),
        org_id=org_id,
        user_type=c.get("custom:user_type"),
        household_id=c.get("custom:household_id") or None,
    )


def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if not body:
        return {}
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise HttpError(400, f"invalid json: {e}") from e
    return body


def path_param(event: dict[str, Any], name: str) -> str:
    val = (event.get("pathParameters") or {}).get(name)
    if not val:
        raise HttpError(400, f"missing path parameter: {name}")
    return val


def query_param(event: dict[str, Any], name: str, default: str | None = None) -> str | None:
    return (event.get("queryStringParameters") or {}).get(name, default)


def response(status: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def new_id() -> str:
    """uuid4 hexを返す。SKで時系列が必要な箇所はtimestampを別フィールドに持つ。"""
    return uuid.uuid4().hex


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_audit_log(
    entity_type: str,
    entity_id: str,
    action: str,
    caller: Caller,
    before: Any = None,
    after: Any = None,
) -> None:
    """全エンティティ編集を AuditLog に追記。

    spec.md §3.4: 「全エンティティに createdBy/createdAt/updatedBy/updatedAt を記録」
    かつ「編集履歴は別テーブル AuditLog に時系列追記」
    """
    try:
        table("AUDIT_LOG_TABLE").put_item(
            Item={
                "entity_key": f"{caller.org_id}#{entity_type}#{entity_id}",
                "timestamp": iso_now(),
                "actor_user_id": caller.user_id,
                "actor_email": caller.email or "",
                "action": action,  # create | update | delete
                "before": before,
                "after": after,
            }
        )
    except Exception:
        # 監査ログ失敗は本処理を止めない(ログ出すのみ)
        logger.exception("audit log write failed: %s %s", entity_type, entity_id)


def handler_wrapper(
    fn: Callable[[dict[str, Any], Caller], dict[str, Any]],
) -> Callable[[dict[str, Any], Any], dict[str, Any]]:
    """全Lambdaの共通ラッパー。例外をHTTPレスポンスへ変換する。"""

    def wrapped(event: dict[str, Any], _context: Any) -> dict[str, Any]:
        try:
            caller = caller_from_event(event)
            return fn(event, caller)
        except HttpError as e:
            logger.warning("http error %s: %s", e.status, e.message)
            return response(e.status, {"error": e.message})
        except Exception as e:  # noqa: BLE001
            logger.exception("unhandled error")
            return response(500, {"error": "internal server error", "detail": str(e)})

    return wrapped

"""POST /meetings/{minute_id}/summarize — 議事録をClaudeで要約。

入力: 議事録の title/agenda/decisions/body
出力: 3行サマリ・議題タグ・主要決定事項を抽出して minute レコードに保存。
"""
from __future__ import annotations

import json
from typing import Any

from common.bedrock import invoke_claude_json
from common.lambda_base import (
    Caller,
    HttpError,
    handler_wrapper,
    iso_now,
    path_param,
    response,
    table,
    write_audit_log,
)

_SYSTEM = (
    "あなたは学童保育所の議事録要約アシスタントです。"
    "保護者会・運営委員会・総会など民主的運営の文脈を理解し、"
    "次のJSON形式で正確に応答してください。余計な前置きやマークダウンフェンスは不要です。\n"
    '{"summary_lines": ["3行以内"], "topic_tags": ["短いラベル"], "key_decisions": ["決定事項"], "follow_ups": ["次回までの宿題"]}'
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can summarize meetings")

    minute_id = path_param(event, "minute_id")
    res = table("MEETING_MINUTES_TABLE").get_item(
        Key={"org_id": caller.org_id, "minute_id": minute_id}
    )
    if "Item" not in res:
        raise HttpError(404, "minute not found")
    m = res["Item"]

    user_msg = (
        f"# {m.get('title','')}\n"
        f"開催日: {m.get('meeting_date','')}\n"
        f"種別: {m.get('meeting_type','')}\n\n"
        f"## 議題\n{m.get('agenda','')}\n\n"
        f"## 決定事項(下書き)\n{m.get('decisions','')}\n\n"
        f"## 本文\n{m.get('body','')}\n"
    )

    try:
        parsed = invoke_claude_json(_SYSTEM, user_msg, max_tokens=1024)
    except json.JSONDecodeError as e:
        raise HttpError(502, f"AI response was not valid JSON: {e}") from e

    now = iso_now()
    table("MEETING_MINUTES_TABLE").update_item(
        Key={"org_id": caller.org_id, "minute_id": minute_id},
        UpdateExpression=(
            "SET ai_summary = :s, ai_tags = :t, ai_decisions = :d, "
            "ai_follow_ups = :f, ai_summarized_at = :a, ai_summarized_by = :u"
        ),
        ExpressionAttributeValues={
            ":s": parsed.get("summary_lines", []),
            ":t": parsed.get("topic_tags", []),
            ":d": parsed.get("key_decisions", []),
            ":f": parsed.get("follow_ups", []),
            ":a": now,
            ":u": caller.user_id,
        },
    )
    write_audit_log("meeting_minute", minute_id, "ai_summarize", caller, after=parsed)
    return response(200, {"minute_id": minute_id, "summary": parsed})


handler = handler_wrapper(_impl)

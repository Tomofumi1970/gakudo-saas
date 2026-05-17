"""Bedrock(Claude)呼び出しヘルパー。

spec.md §7 AI支援機能:
- 引継ぎ文書生成
- 議事録要約
- 保育日誌サマリ等

MVP は Claude Haiku 4.5 を ap-northeast-1 で利用(高速・低コスト)。
モデル切替は環境変数 BEDROCK_MODEL_ID で可能。
"""
from __future__ import annotations

import json
import os
from typing import Any

import boto3

_bedrock = boto3.client(
    "bedrock-runtime",
    region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
)


def invoke_claude(
    system: str,
    user_message: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str:
    """単一ユーザーメッセージで Claude を呼び出してテキスト応答を返す。"""
    # 新しい Claude モデルは inference profile 経由でしか呼べない。
    # 既定は日本リージョン優先プロファイル(jp.anthropic.*)を使用。
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user_message}],
    }
    res = _bedrock.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(res["body"].read())
    parts = payload.get("content", [])
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def invoke_claude_json(
    system: str,
    user_message: str,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """JSON応答を期待する呼び出し(systemに「JSONで返す」旨を入れる前提)。"""
    raw = invoke_claude(system, user_message, max_tokens=max_tokens, temperature=0.1)
    # ```json ... ``` のフェンスが付くケースに対応
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)
        if len(raw) >= 3:
            raw = raw[1]
            if raw.startswith("json\n"):
                raw = raw[5:]
        else:
            raw = "".join(raw)
    return json.loads(raw)

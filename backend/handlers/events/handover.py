"""POST /events/{event_id}/handover — 次年度実行委員向け引継ぎ書を Claude で生成。

入力: 当該 event + 同名(または近い名前)の過去 event の参加者・精算結果・反省点
出力: マークダウンの引継ぎ文書(構成・準備物・予算感・スケジュール・注意点)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from common.bedrock import invoke_claude
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
    "あなたは学童保育所の行事(キャンプ・夏まつり等)実行委員の引継ぎ文書を作成するアシスタントです。"
    "翌年度の保護者役員が読んで具体的に動けるよう、過去の数字(参加人数・実費・余剰金・按分)と"
    "学びを織り込んだマークダウン文書を作成してください。\n"
    "出力構成: \n"
    "# 行事概要\n"
    "## 開催実績(過去)\n"
    "## 予算と実費\n"
    "## スケジュール\n"
    "## 準備物・役割分担\n"
    "## 注意点・改善提案\n"
    "## 次年度に向けて\n"
)


def _impl(event: dict[str, Any], caller: Caller) -> dict[str, Any]:
    if caller.user_type not in ("staff", "operator"):
        raise HttpError(403, "only staff can generate handover")

    event_id = path_param(event, "event_id")
    ev_res = table("EVENTS_TABLE").get_item(
        Key={"org_id": caller.org_id, "event_id": event_id}
    )
    if "Item" not in ev_res:
        raise HttpError(404, "event not found")
    target = ev_res["Item"]

    # 同名(完全一致)の過去 event を抽出 — 規模が小さいので scan
    all_events_res = table("EVENTS_TABLE").query(
        KeyConditionExpression=Key("org_id").eq(caller.org_id),
    )
    same_name = [
        e
        for e in all_events_res.get("Items", [])
        if e.get("name") == target.get("name")
    ]
    same_name.sort(key=lambda e: e.get("event_date", ""), reverse=True)

    # 各 event の参加者を取得
    summaries: list[str] = []
    for e in same_name[:5]:  # 直近5回まで
        pk = f"{caller.org_id}#{e['event_id']}"
        p_res = table("EVENT_PARTICIPANTS_TABLE").query(
            KeyConditionExpression=Key("org_event").eq(pk),
        )
        participants = p_res.get("Items", [])
        planned_sum = sum(
            (Decimal(str(p.get("planned_charge", 0))) for p in participants),
            Decimal("0"),
        )
        actual_total = Decimal(str(e.get("actual_total", 0)))
        summaries.append(
            f"- {e['event_date']} {e['name']}: 参加 {len(participants)}名 / "
            f"見込合計 ¥{int(planned_sum):,} / 実費 ¥{int(actual_total):,} / "
            f"status {e.get('status','-')}"
        )

    user_msg = (
        f"# 対象行事\n名称: {target.get('name')}\n開催予定日: {target.get('event_date')}\n"
        f"説明: {target.get('description','')}\n\n"
        f"# 過去の同名行事の実績\n" + ("\n".join(summaries) if summaries else "(過去実績なし、初回開催)") + "\n\n"
        "上記を踏まえ、次の実行委員(保護者役員)が読んで具体的に準備に取り掛かれる引継ぎ文書を作成してください。"
    )

    text = invoke_claude(_SYSTEM, user_msg, max_tokens=1024, temperature=0.4)

    now = iso_now()
    table("EVENTS_TABLE").update_item(
        Key={"org_id": caller.org_id, "event_id": event_id},
        UpdateExpression="SET ai_handover_md = :m, ai_handover_at = :t, ai_handover_by = :u",
        ExpressionAttributeValues={
            ":m": text, ":t": now, ":u": caller.user_id,
        },
    )
    write_audit_log(
        "event", event_id, "ai_handover", caller, after={"length": len(text)}
    )
    return response(
        200, {"event_id": event_id, "handover_md": text, "based_on_events": len(summaries)}
    )


handler = handler_wrapper(_impl)

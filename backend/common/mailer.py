"""SES 経由のメール送信ユーティリティ。

spec.md §6 通知はメールのみ(SES 1本)。
STG では SES sandbox により送信先も verified である必要がある(本番化は別途運用申請)。
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

import boto3

logger = logging.getLogger()
_ses = boto3.client("ses")


def send_email(
    to: str | Iterable[str],
    subject: str,
    body_text: str,
    body_html: str | None = None,
    reply_to: str | None = None,
) -> dict:
    from_email = os.environ["FROM_EMAIL"]
    to_list = [to] if isinstance(to, str) else list(to)

    message: dict = {
        "Subject": {"Data": subject, "Charset": "UTF-8"},
        "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
    }
    if body_html:
        message["Body"]["Html"] = {"Data": body_html, "Charset": "UTF-8"}

    params: dict = {
        "Source": from_email,
        "Destination": {"ToAddresses": to_list},
        "Message": message,
    }
    if reply_to:
        params["ReplyToAddresses"] = [reply_to]

    try:
        return _ses.send_email(**params)
    except Exception as e:
        # SES sandbox や未承認アドレスの場合はここで失敗する。呼び出し側は
        # 発行処理自体は完了させ、メール送信失敗のみ記録するのが妥当。
        logger.exception("send_email failed: to=%s subject=%s", to_list, subject)
        raise

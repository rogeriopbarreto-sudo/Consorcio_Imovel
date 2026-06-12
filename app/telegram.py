"""Notificações via Telegram Bot API. Nunca levanta exceção — loga e segue."""
from __future__ import annotations

import logging

import requests

from .config import settings

log = logging.getLogger(__name__)


def configurado() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def enviar(texto: str) -> bool:
    """Envia mensagem em HTML. Retorna True se aceita pelo Telegram."""
    if not configurado():
        log.info("Telegram não configurado — mensagem suprimida.")
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": settings.telegram_chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        ok = resp.ok and resp.json().get("ok", False)
        if not ok:
            log.error("Telegram recusou: %s", resp.text[:300])
        return ok
    except Exception as exc:
        log.error("Falha ao enviar Telegram: %s", exc)
        return False

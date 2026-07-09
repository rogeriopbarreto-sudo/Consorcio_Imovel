"""Dispara uma tentativa de busca no processo web local.

Feito para o Scheduled Task do Coolify:
    comando: python scripts/tick.py
    agenda:  */10 * * * *   (a cada 10 min)

O tick bate em /run-check no próprio processo web (localhost) para que o
dashboard em memória fique fresco. Todo o gate — dia de sorteio, janela de
horário (20h–22h BRT) e limite de 10 tentativas — vive no app, então o
scheduler só precisa disparar de 10 em 10 min; fora da janela o app responde
com no-op.
"""
from __future__ import annotations

import os
import sys

import requests

PORT = os.environ.get("PORT", "8000")
SECRET = os.environ.get("CRON_SECRET", "")
URL = f"http://127.0.0.1:{PORT}/run-check"


def main() -> int:
    try:
        resp = requests.get(URL, params={"secret": SECRET}, timeout=90)
        print(resp.status_code, resp.text[:500])
        return 0 if resp.ok else 1
    except Exception as exc:  # rede/timeout — só loga, o próximo tick tenta
        print(f"tick falhou: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

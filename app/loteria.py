"""Busca o resultado da Loteria Federal na API JSON oficial da Caixa.

Endpoint descoberto no protótipo: muito mais confiável que raspar o
portal .aspx (que depende de JavaScript pesado).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime

import requests

from .models import ResultadoLoteria

log = logging.getLogger(__name__)

URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api/federal"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; ConsorciosControl/1.0)",
}
TENTATIVAS = 3
TIMEOUT = 20


class LoteriaIndisponivel(Exception):
    """API da Caixa fora do ar ou resposta inválida."""


def buscar_resultado() -> ResultadoLoteria:
    """Último resultado da Federal. Levanta LoteriaIndisponivel após retries."""
    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            dados = resp.json()
            premios = [re.sub(r"\D", "", str(p)) for p in dados["listaDezenas"]]
            if len(premios) < 5 or any(len(p) < 5 for p in premios):
                raise ValueError(f"listaDezenas inesperada: {dados['listaDezenas']}")
            return ResultadoLoteria(
                concurso=int(dados["numero"]),
                data=datetime.strptime(dados["dataApuracao"], "%d/%m/%Y").date(),
                premios=premios[:5],
                origem="caixa",
            )
        except Exception as exc:  # rede, JSON, schema — tudo vira retry
            ultimo_erro = exc
            log.warning("Tentativa %s/%s falhou: %s", tentativa, TENTATIVAS, exc)
            if tentativa < TENTATIVAS:
                time.sleep(2 * tentativa)
    raise LoteriaIndisponivel(str(ultimo_erro))

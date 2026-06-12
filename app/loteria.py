"""Busca o resultado da Loteria Federal com fontes em cascata.

1. API JSON oficial da Caixa (servicebus2) — bloqueia IPs de datacenter
   estrangeiro (403 no Render), mas é a fonte canônica quando acessível.
2. Espelho comunitário loteriascaixa-api — mesmos dados, sem geo-bloqueio.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime

import requests

from .models import ResultadoLoteria

log = logging.getLogger(__name__)

URL_CAIXA = "https://servicebus2.caixa.gov.br/portaldeloterias/api/federal"
URL_ESPELHO = "https://loteriascaixa-api.herokuapp.com/api/federal/latest"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
}
RODADAS = 2
TIMEOUT = 20


class LoteriaIndisponivel(Exception):
    """Nenhuma fonte respondeu com um resultado válido."""


def _premios(lista: list) -> list[str]:
    """Normaliza para 5 prêmios de exatamente 5 dígitos (bilhete da Federal)."""
    premios = [re.sub(r"\D", "", str(p))[-5:].zfill(5) for p in lista]
    if len(premios) < 5 or any(len(p) != 5 for p in premios):
        raise ValueError(f"lista de prêmios inesperada: {lista}")
    return premios[:5]


def _parse_caixa(dados: dict) -> ResultadoLoteria:
    return ResultadoLoteria(
        concurso=int(dados["numero"]),
        data=datetime.strptime(dados["dataApuracao"], "%d/%m/%Y").date(),
        premios=_premios(dados["listaDezenas"]),
        origem="caixa",
    )


def _parse_espelho(dados: dict) -> ResultadoLoteria:
    return ResultadoLoteria(
        concurso=int(dados["concurso"]),
        data=datetime.strptime(dados["data"], "%d/%m/%Y").date(),
        premios=_premios(dados["dezenas"]),
        origem="espelho",
    )


FONTES = [
    ("caixa", URL_CAIXA, _parse_caixa),
    ("espelho", URL_ESPELHO, _parse_espelho),
]


def buscar_resultado() -> ResultadoLoteria:
    """Último resultado da Federal. Levanta LoteriaIndisponivel se todas as
    fontes falharem em todas as rodadas."""
    ultimo_erro: Exception | None = None
    for rodada in range(1, RODADAS + 1):
        for nome, url, parse in FONTES:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                resp.raise_for_status()
                return parse(resp.json())
            except Exception as exc:  # rede, JSON, schema — tenta a próxima
                ultimo_erro = exc
                log.warning("Fonte %s falhou (rodada %s/%s): %s",
                            nome, rodada, RODADAS, exc)
        if rodada < RODADAS:
            time.sleep(2 * rodada)
    raise LoteriaIndisponivel(str(ultimo_erro))

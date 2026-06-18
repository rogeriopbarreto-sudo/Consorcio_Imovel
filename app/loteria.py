"""Busca o resultado da Loteria Federal com fontes em cascata.

1. API JSON oficial da Caixa (servicebus2) — fonte canônica e sempre fresca,
   mas bloqueia IPs de datacenter estrangeiro (403 a partir do servidor).
2. Caixa via proxy público (allorigins) — mesma resposta oficial, mas buscada
   pela infra do proxy, contornando o geo-bloqueio. Fresca como a oficial.
3. Espelho comunitário loteriascaixa-api — último recurso; costuma ficar
   defasado em dias, então só vale quando bate com a data esperada.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from urllib.parse import quote

import requests

from .models import ResultadoLoteria

log = logging.getLogger(__name__)

URL_CAIXA = "https://servicebus2.caixa.gov.br/portaldeloterias/api/federal"
URL_CAIXA_PROXY = "https://api.allorigins.win/raw?url=" + quote(URL_CAIXA, safe="")
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
    ("caixa-proxy", URL_CAIXA_PROXY, _parse_caixa),
    ("espelho", URL_ESPELHO, _parse_espelho),
]


def buscar_resultado(data_esperada: date | None = None) -> ResultadoLoteria:
    """Último resultado da Federal, em cascata.

    Quando `data_esperada` é dada, devolve a primeira fonte cujo resultado bate
    com essa data — assim um espelho defasado nunca mascara um sorteio já
    publicado na Caixa. Sem nenhum match exato, devolve o resultado mais recente
    que conseguiu obter (e quem chama decide se serve). Levanta
    LoteriaIndisponivel só se nenhuma fonte responder.
    """
    ultimo_erro: Exception | None = None
    candidatos: list[ResultadoLoteria] = []
    for rodada in range(1, RODADAS + 1):
        for nome, url, parse in FONTES:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                resp.raise_for_status()
                res = parse(resp.json())
            except Exception as exc:  # rede, JSON, schema — tenta a próxima
                ultimo_erro = exc
                log.warning("Fonte %s falhou (rodada %s/%s): %s",
                            nome, rodada, RODADAS, exc)
                continue
            if data_esperada is None or res.data == data_esperada:
                return res
            log.info("Fonte %s trouxe %s, esperado %s — defasada, seguindo",
                     nome, res.data, data_esperada)
            candidatos.append(res)
        if rodada < RODADAS:
            time.sleep(2 * rodada)
    if candidatos:  # nenhuma bateu a data; devolve a mais recente obtida
        return max(candidatos, key=lambda r: r.data)
    raise LoteriaIndisponivel(str(ultimo_erro))

"""Busca o resultado da Loteria Federal com fontes e proxies em cascata.

O endpoint oficial da Caixa é a fonte canônica, mas:
1. bloqueia IPs de datacenter estrangeiro (403 a partir do servidor Hetzner);
2. o endpoint "latest" (`/api/federal`) costuma **atrasar** — segue servindo o
   concurso anterior por horas depois de o novo já estar publicado no site, que
   consulta por número (`/api/federal/{n}`).

Por isso a busca tem duas camadas:
- **latest** em cascata: Caixa direta → proxies públicos → espelho comunitário;
- **sondagem por número**: quando esperamos uma data e o latest está atrasado,
  tenta os próximos concursos (`base+1`, `base+2`...) pelo endpoint numerado,
  exatamente como o site — assim um "latest" preguiçoso não mascara o sorteio.

A Caixa é sempre buscada por uma lista de proxies (direto + allorigins +
codetabs); o primeiro que responder vence. O ciclo de 10 min do scheduler é o
retry externo, então aqui não há sleep/rodadas.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from urllib.parse import quote

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
TIMEOUT = 20
# Quantos concursos à frente do último conhecido sondar quando o latest atrasa.
SONDAR_MAX = 3


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


def _get_json(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _proxies(alvo: str) -> list[tuple[str, str]]:
    """URLs para alcançar um endpoint da Caixa: direto + proxies públicos.

    Direto é o mais fresco quando o IP não é bloqueado (local); no servidor
    (geo-bloqueio 403) valem os proxies. allorigins é o mais confiável;
    codetabs entra quando allorigins está fora.
    """
    enc = quote(alvo, safe="")
    return [
        ("caixa", alvo),
        ("allorigins", f"https://api.allorigins.win/raw?url={enc}"),
        ("codetabs", f"https://api.codetabs.com/v1/proxy/?quest={enc}"),
    ]


def _caixa(caminho: str = "") -> ResultadoLoteria | None:
    """Resultado da Caixa em `/api/federal{caminho}` pelo primeiro proxy que
    responder. None se todos falharem (rede, geo-bloqueio ou concurso inexistente)."""
    for nome, url in _proxies(URL_CAIXA + caminho):
        try:
            return _parse_caixa(_get_json(url))
        except Exception as exc:
            log.warning("Caixa%s via %s falhou: %s", caminho, nome, exc)
    return None


def buscar_resultado(data_esperada: date | None = None) -> ResultadoLoteria:
    """Último resultado da Federal, com sondagem por número quando preciso.

    Sem `data_esperada`, devolve o latest mais fresco que conseguir. Com
    `data_esperada`, devolve a primeira fonte cujo resultado bate com a data;
    se o latest estiver atrasado, sonda os próximos concursos pelo endpoint
    numerado (como o site) até achar a data esperada. Sem nenhum match, devolve
    o resultado mais recente obtido (quem chama decide se serve). Levanta
    LoteriaIndisponivel só se nenhuma fonte responder.
    """
    candidatos: list[ResultadoLoteria] = []
    ultimo_erro: Exception | None = None

    # 1. Caixa latest (direto + proxies)
    res = _caixa()
    if res is not None:
        if data_esperada is None or res.data == data_esperada:
            return res
        candidatos.append(res)

    # 2. Espelho comunitário (não é geo-bloqueado; costuma atrasar)
    try:
        res = _parse_espelho(_get_json(URL_ESPELHO))
        if data_esperada is None or res.data == data_esperada:
            return res
        candidatos.append(res)
    except Exception as exc:
        ultimo_erro = exc
        log.warning("Espelho falhou: %s", exc)

    # 3. Latest atrasado: sonda os próximos concursos pelo número (como o site)
    if data_esperada is not None and candidatos:
        base = max(c.concurso for c in candidatos)
        for n in range(base + 1, base + 1 + SONDAR_MAX):
            res = _caixa(f"/{n}")
            if res is None:
                break  # concurso ainda não existe (500) ou proxies fora
            candidatos.append(res)
            if res.data == data_esperada:
                return res
            if res.data > data_esperada:
                break  # já passou da data esperada

    if candidatos:  # nenhuma bateu a data; devolve a mais recente obtida
        return max(candidatos, key=lambda r: r.data)
    raise LoteriaIndisponivel(str(ultimo_erro))

"""Persistência em Google Sheets via gspread (service account).

Seis abas: consorcios, calendario, resultados, analises, notificacoes, log.
Todas as funções degradam graciosamente: sem credenciais o app continua
funcionando (dashboard renderiza, análise roda em memória).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import settings
from .models import EventoCalendario, ResultadoLoteria

log = logging.getLogger(__name__)

ABAS = {
    "consorcios": ["id", "nome", "grupo", "cota", "unidade", "regra_json"],
    "calendario": ["consorcio_id", "vencimento", "extracao",
                   "oferta_lance", "assembleia", "chamadas"],
    "resultados": ["data_extracao", "concurso", "p1", "p2", "p3", "p4", "p5",
                   "origem", "created_at"],
    "analises": ["data_extracao", "consorcio_id", "contemplado",
                 "ordem_contemplada", "melhor_ordem", "melhor_numero",
                 "numero_usuario", "distancia", "direcao",
                 "detalhe_json", "created_at"],
    "notificacoes": ["data_extracao", "consorcio_id", "tipo", "created_at"],
    "log": ["timestamp", "evento", "detalhe"],
}

_CACHE: dict = {"planilha": None, "registros": {}, "ts": {}}
CACHE_TTL = 60  # segundos


class SheetsIndisponivel(Exception):
    """Credenciais ausentes ou planilha inacessível."""


def configurado() -> bool:
    return bool(settings.google_service_account_json and settings.google_sheet_id)


def _agora() -> str:
    return datetime.now(ZoneInfo(settings.app_timezone)).strftime("%Y-%m-%d %H:%M:%S")


def _planilha():
    if not configurado():
        raise SheetsIndisponivel("GOOGLE_SERVICE_ACCOUNT_JSON/GOOGLE_SHEET_ID ausentes")
    if _CACHE["planilha"] is None:
        import gspread
        creds = json.loads(settings.google_service_account_json)
        client = gspread.service_account_from_dict(creds)
        _CACHE["planilha"] = client.open_by_key(settings.google_sheet_id)
    return _CACHE["planilha"]


def _aba(nome: str):
    pl = _planilha()
    try:
        return pl.worksheet(nome)
    except Exception:
        ws = pl.add_worksheet(title=nome, rows=200, cols=len(ABAS[nome]) + 2)
        ws.append_row(ABAS[nome])
        return ws


def _registros(nome: str, ttl: int = CACHE_TTL) -> list[dict]:
    """get_all_records com cache leve para não estourar cota da API."""
    agora = time.time()
    if nome in _CACHE["registros"] and agora - _CACHE["ts"].get(nome, 0) < ttl:
        return _CACHE["registros"][nome]
    dados = _aba(nome).get_all_records()
    _CACHE["registros"][nome] = dados
    _CACHE["ts"][nome] = agora
    return dados


def _invalidar(nome: str) -> None:
    _CACHE["ts"].pop(nome, None)


# ---------- escrita ----------

def registrar_resultado(res: ResultadoLoteria) -> None:
    chave = res.data.isoformat()
    if any(str(r.get("data_extracao")) == chave for r in _registros("resultados")):
        return
    _aba("resultados").append_row(
        [chave, res.concurso, *res.premios, res.origem, _agora()])
    _invalidar("resultados")


def registrar_analise(data_ext: date, consorcio_id: str, payload: dict) -> None:
    if ja_analisado(data_ext, consorcio_id):
        return
    _aba("analises").append_row([
        data_ext.isoformat(), consorcio_id,
        payload.get("contemplado"), payload.get("ordem_contemplada"),
        payload.get("melhor_ordem"), payload.get("melhor_numero"),
        payload.get("numero_usuario"), payload.get("distancia"),
        payload.get("direcao"),
        json.dumps(payload.get("detalhe", {}), ensure_ascii=False),
        _agora(),
    ])
    _invalidar("analises")


def registrar_notificacao(data_ext: date, consorcio_id: str,
                          tipo: str = "telegram") -> None:
    _aba("notificacoes").append_row(
        [data_ext.isoformat(), consorcio_id, tipo, _agora()])
    _invalidar("notificacoes")


def log_evento(evento: str, detalhe: str = "") -> None:
    try:
        _aba("log").append_row([_agora(), evento, detalhe[:500]])
    except Exception as exc:
        log.warning("log_evento falhou: %s", exc)


# ---------- leitura / dedup ----------

def ja_analisado(data_ext: date, consorcio_id: str) -> bool:
    chave = data_ext.isoformat()
    return any(str(r.get("data_extracao")) == chave
               and str(r.get("consorcio_id")) == consorcio_id
               for r in _registros("analises"))


def ja_notificado(data_ext: date, consorcio_id: str,
                  tipo: str = "telegram") -> bool:
    chave = data_ext.isoformat()
    return any(str(r.get("data_extracao")) == chave
               and str(r.get("consorcio_id")) == consorcio_id
               and str(r.get("tipo")) == tipo
               for r in _registros("notificacoes"))


def ultimo_resultado() -> dict | None:
    registros = _registros("resultados")
    return registros[-1] if registros else None


def analises_da_data(data_ext: str) -> list[dict]:
    return [r for r in _registros("analises")
            if str(r.get("data_extracao")) == data_ext]


def calendario_remoto() -> list[EventoCalendario] | None:
    """Calendário editável na própria planilha. None se indisponível/vazio."""
    try:
        registros = _registros("calendario", ttl=300)
    except Exception:
        return None
    eventos = []
    for r in registros:
        try:
            eventos.append(EventoCalendario(
                consorcio_id=str(r["consorcio_id"]),
                vencimento=r.get("vencimento") or None,
                extracao=r["extracao"],
                oferta_lance=r.get("oferta_lance") or None,
                assembleia=r.get("assembleia") or None,
                chamadas=[c.strip() for c in str(r.get("chamadas", "")).split(";")
                          if c.strip()],
            ))
        except Exception as exc:
            log.warning("Linha de calendário inválida ignorada: %s (%s)", r, exc)
    return eventos or None

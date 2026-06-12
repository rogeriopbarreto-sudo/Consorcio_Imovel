"""Pipeline run_check: extração hoje? → buscar → analisar → Sheets → Telegram."""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import loteria, matching, sheets, telegram
from .config import carregar_calendario_local, carregar_consorcios, settings
from .models import Consorcio, EventoCalendario, ResultadoLoteria

log = logging.getLogger(__name__)

# Estado em memória: alimenta o dashboard mesmo sem Sheets configurado.
ESTADO: dict = {
    "resultado": None,        # ResultadoLoteria
    "analises": {},           # consorcio_id -> matching.Analise
    "atualizado_em": None,    # datetime
    "erro": None,             # str | None
}

MESES_PT = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def hoje_tz() -> date:
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


def calendario() -> list[EventoCalendario]:
    """Calendário da aba `calendario` do Sheets; fallback no JSON local."""
    if sheets.configurado():
        remoto = sheets.calendario_remoto()
        if remoto:
            return remoto
    return carregar_calendario_local()


def eventos_na_data(d: date) -> list[EventoCalendario]:
    return [e for e in calendario() if e.extracao == d]


def proximos_eventos(apos: date, n: int = 4) -> list[EventoCalendario]:
    futuros = sorted((e for e in calendario() if e.extracao >= apos),
                     key=lambda e: e.extracao)
    return futuros[:n]


def _fmt_data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _mensagem_telegram(cons: Consorcio, analise: matching.Analise,
                       res: ResultadoLoteria) -> str:
    cab = (f"🎰 <b>Loteria Federal {_fmt_data(res.data)}</b> "
           f"(concurso {res.concurso})\n"
           f"{cons.emoji} <b>{cons.nome}</b> — Grupo {cons.grupo} · "
           f"Cota {cons.cota}\n\n")
    if analise.contemplado:
        m = analise.melhor
        corpo = (f"🎉 <b>COTA CONTEMPLADA!</b>\n"
                 f"O {m.ordem}º prêmio tirou {cons.unidade} <b>{m.numero}</b>, "
                 f"que corresponde à sua cota.\n\n"
                 f"⚠️ Análise matemática — confirme com a Ademicon.")
    elif analise.melhor is not None:
        m = analise.melhor
        corpo = (f"Não foi dessa vez.\n"
                 f"Mais perto: {m.ordem}º prêmio, {cons.unidade} "
                 f"<b>{m.numero}</b> — a <b>{m.distancia}</b> "
                 f"({m.direcao}) do seu <b>{m.numero_usuario}</b>.")
    else:
        corpo = "Nenhum prêmio válido para análise nesta extração."
    proximos = [e for e in proximos_eventos(res.data)
                if e.consorcio_id == cons.id and e.extracao > res.data]
    if proximos:
        corpo += f"\n\n📅 Próxima extração: {_fmt_data(proximos[0].extracao)}"
    return cab + corpo


def _analise_payload(analise: matching.Analise) -> dict:
    m = analise.melhor
    return {
        "contemplado": analise.contemplado,
        "ordem_contemplada": analise.ordem_contemplada,
        "melhor_ordem": m.ordem if m else None,
        "melhor_numero": m.numero if m else None,
        "numero_usuario": m.numero_usuario if m else None,
        "distancia": m.distancia if m else None,
        "direcao": m.direcao if m else None,
        "detalhe": {"premios": [asdict(p) for p in analise.premios]},
    }


def _processar(res: ResultadoLoteria, alvos: list[Consorcio]) -> dict:
    """Analisa, grava em Sheets e notifica (com dedup). Atualiza ESTADO."""
    resumo: dict = {}
    ESTADO["resultado"] = res
    ESTADO["atualizado_em"] = datetime.now(ZoneInfo(settings.app_timezone))
    ESTADO["erro"] = None

    sheets_ok = sheets.configurado()
    if sheets_ok:
        try:
            sheets.registrar_resultado(res)
        except Exception as exc:
            sheets_ok = False
            log.error("Sheets indisponível: %s", exc)
            ESTADO["erro"] = f"Sheets indisponível: {exc}"

    for cons in alvos:
        analise = matching.analisar(cons.cota, cons.regra.como_regra(),
                                    res.premios)
        ESTADO["analises"][cons.id] = analise
        payload = _analise_payload(analise)
        resumo[cons.id] = {k: payload[k] for k in
                           ("contemplado", "melhor_ordem", "melhor_numero",
                            "numero_usuario", "distancia", "direcao")}

        if sheets_ok:
            try:
                sheets.registrar_analise(res.data, cons.id, payload)
            except Exception as exc:
                log.error("Falha ao gravar análise: %s", exc)

        # Telegram com dedup por (data_extracao, consorcio_id)
        try:
            ja_enviado = sheets_ok and sheets.ja_notificado(res.data, cons.id)
        except Exception:
            ja_enviado = False
        if not ja_enviado and telegram.enviar(_mensagem_telegram(cons, analise, res)):
            if sheets_ok:
                try:
                    sheets.registrar_notificacao(res.data, cons.id)
                except Exception as exc:
                    log.error("Falha ao registrar notificação: %s", exc)

    if sheets_ok:
        sheets.log_evento("run_check", f"data={res.data} concurso={res.concurso} "
                                       f"alvos={[c.id for c in alvos]}")
    return resumo


def _avisar_falha(d: date, motivo: str) -> None:
    """Aviso de falha no Telegram, no máximo 1x por data."""
    ESTADO["erro"] = motivo
    try:
        if sheets.configurado() and sheets.ja_notificado(d, "_falha"):
            return
    except Exception:
        pass
    if telegram.enviar(f"⚠️ <b>Consórcios Control</b>\n{motivo}\n"
                       f"Use o input manual no dashboard se necessário."):
        try:
            if sheets.configurado():
                sheets.registrar_notificacao(d, "_falha")
        except Exception:
            pass


def run_check(force: bool = False, data_str: str | None = None) -> dict:
    """Entrada principal (cron externo e botão Atualizar).

    force=True analisa mesmo sem extração no calendário e aceita
    resultado de data diferente da esperada.
    """
    d = date.fromisoformat(data_str) if data_str else hoje_tz()
    eventos = eventos_na_data(d)
    todos = carregar_consorcios()
    alvos = [c for c in todos if any(e.consorcio_id == c.id for e in eventos)]
    if not alvos:
        if not force:
            return {"status": "sem_extracao_hoje", "data": d.isoformat()}
        alvos = todos

    try:
        res = loteria.buscar_resultado()
    except loteria.LoteriaIndisponivel as exc:
        _avisar_falha(d, f"API da Caixa indisponível em {_fmt_data(d)}: {exc}")
        return {"status": "loteria_indisponivel", "data": d.isoformat(),
                "erro": str(exc)}

    if res.data != d and not force:
        _avisar_falha(d, f"Resultado ainda não apurado para {_fmt_data(d)} "
                         f"(último: {_fmt_data(res.data)}).")
        return {"status": "resultado_de_outra_data", "data": d.isoformat(),
                "data_apuracao": res.data.isoformat()}

    resumo = _processar(res, alvos)
    return {"status": "ok", "data": res.data.isoformat(),
            "concurso": res.concurso, "origem": res.origem,
            "analises": resumo}


def registrar_manual(data_str: str, premios: list[str],
                     concurso: int = 0) -> dict:
    """Fallback: usuário digita os 5 prêmios no dashboard."""
    res = ResultadoLoteria(concurso=concurso,
                           data=date.fromisoformat(data_str),
                           premios=premios, origem="manual")
    resumo = _processar(res, carregar_consorcios())
    return {"status": "ok", "data": res.data.isoformat(),
            "origem": "manual", "analises": resumo}


def carregar_estado_inicial() -> None:
    """No cold start, repõe o último resultado gravado no Sheets."""
    if ESTADO["resultado"] is not None or not sheets.configurado():
        return
    try:
        ultimo = sheets.ultimo_resultado()
        if not ultimo:
            return
        res = ResultadoLoteria(
            concurso=int(ultimo.get("concurso") or 0),
            data=date.fromisoformat(str(ultimo["data_extracao"])),
            premios=[str(ultimo[f"p{i}"]).zfill(5) for i in range(1, 6)],
            origem=str(ultimo.get("origem") or "caixa"),
        )
        ESTADO["resultado"] = res
        for cons in carregar_consorcios():
            ESTADO["analises"][cons.id] = matching.analisar(
                cons.cota, cons.regra.como_regra(), res.premios)
        ESTADO["atualizado_em"] = datetime.now(ZoneInfo(settings.app_timezone))
    except Exception as exc:
        log.warning("Estado inicial via Sheets falhou: %s", exc)

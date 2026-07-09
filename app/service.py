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
    # Sessão de busca do dia: os ticks do scheduler batem no processo web,
    # então este contador sobrevive entre tentativas sem depender do Sheets.
    "busca": {
        "data": None,         # date da sessão corrente
        "tentativas": 0,      # tentativas sem resultado já notificadas
        "resolvido": False,   # resultado encontrado e processado
        "encerrada": False,   # atingiu o limite de tentativas
    },
}

MESES_PT = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def hoje_tz() -> date:
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


def agora_tz() -> datetime:
    return datetime.now(ZoneInfo(settings.app_timezone))


def _fmt_horario(dt: datetime | None = None) -> str:
    return (dt or agora_tz()).strftime("%d/%m/%Y às %H:%M")


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


def _unidade_cota(cons: Consorcio, p: matching.PremioAnalise) -> str:
    """Ex.: 'milhar <b>3952</b> → cota <b>619</b>'. Mostra a redução ao espaço
    de cotas só quando ela existe (no Veículo centena = cota, sem seta)."""
    txt = f"{cons.unidade} <b>{p.numero}</b>"
    if p.cota_sorteada is not None and p.cota_sorteada != int(p.numero):
        txt += f" → cota <b>{p.cota_sorteada}</b>"
    return txt


def _linha_primeiro_premio(cons: Consorcio, analise: matching.Analise) -> str | None:
    """Linha do 1º prêmio: bilhete, cota sorteada (reduzida) e distância à sua cota."""
    p1 = next((p for p in analise.premios if p.ordem == 1), None)
    if p1 is None:
        return None
    if p1.cota_sorteada is not None:
        return (f"1º prêmio: {p1.bilhete}, {_unidade_cota(cons, p1)} — "
                f"a <b>{p1.distancia}</b> ({p1.direcao}) da sua cota "
                f"<b>{cons.cota}</b>.")
    if p1.eliminado:
        return f"1º prêmio: {p1.bilhete}, {cons.unidade} {p1.numero} (eliminada)."
    return f"1º prêmio: {p1.bilhete} (sem {cons.unidade} válida)."


def _mensagem_telegram(cons: Consorcio, analise: matching.Analise,
                       res: ResultadoLoteria) -> str:
    cab = (f"🎰 <b>Loteria Federal {_fmt_data(res.data)}</b> "
           f"(concurso {res.concurso})\n"
           f"{cons.emoji} <b>{cons.nome}</b> — Grupo {cons.grupo} · "
           f"Cota {cons.cota}\n\n")
    if analise.contemplado:
        m = analise.melhor
        corpo = (f"🎉 <b>COTA CONTEMPLADA!</b>\n"
                 f"O {m.ordem}º prêmio tirou {_unidade_cota(cons, m)}, "
                 f"que é a sua cota <b>{cons.cota}</b>.\n\n"
                 f"⚠️ Análise matemática — confirme com a Ademicon.")
    elif analise.melhor is not None:
        m = analise.melhor
        corpo = "Não foi dessa vez.\n"
        linha1 = _linha_primeiro_premio(cons, analise)
        if linha1:
            corpo += linha1
        # A aproximação ancora no 1º prêmio. Só quando o 1º foi eliminado a
        # âncora é outro prêmio (m.ordem ≠ 1) — aí mostramos a base usada.
        if m.ordem != 1:
            corpo += (f"\nBase do sorteio (1º prêmio eliminado): {m.ordem}º prêmio, "
                      f"{_unidade_cota(cons, m)} — a <b>{m.distancia}</b> "
                      f"({m.direcao}) da sua cota <b>{cons.cota}</b>.")
    else:
        corpo = "Nenhum prêmio válido para análise nesta extração."
    proximos = [e for e in proximos_eventos(res.data)
                if e.consorcio_id == cons.id and e.extracao > res.data]
    if proximos:
        corpo += f"\n\n📅 Próxima extração: {_fmt_data(proximos[0].extracao)}"
    corpo += f"\n\n🕒 Verificado em {_fmt_horario()}"
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


def _dentro_janela(agora: datetime) -> bool:
    """Hora local dentro da janela de busca do dia de sorteio."""
    return settings.busca_hora_inicio <= agora.hour < settings.busca_hora_fim


def _reset_busca(d: date) -> dict:
    """Zera a sessão de busca ao virar o dia; devolve o estado corrente."""
    b = ESTADO["busca"]
    if b["data"] != d:
        b.update(data=d, tentativas=0, resolvido=False, encerrada=False)
    return b


def _msg_tentativa(d: date, n: int, maxt: int, motivo: str) -> str:
    return (f"🔍 <b>Consórcios Control</b> — busca do dia\n"
            f"Tentativa <b>{n}/{maxt}</b>: resultado da Loteria Federal para "
            f"{_fmt_data(d)} ainda não publicado.\n"
            f"{motivo}\n"
            f"Tento de novo em ~10 min.\n"
            f"🕒 {_fmt_horario()}")


def _msg_encerrada(d: date, maxt: int) -> str:
    return (f"⛔ <b>Consórcios Control</b>\n"
            f"Encerrei a busca de hoje após {maxt} tentativas — o resultado de "
            f"{_fmt_data(d)} não saiu a tempo.\n"
            f"Assim que sair, use o botão <b>Atualizar agora</b> ou o input "
            f"manual no dashboard.\n"
            f"🕒 {_fmt_horario()}")


def _sem_resultado(d: date, motivo: str, force: bool) -> dict:
    """Trata um tick sem resultado.

    Nos ticks automáticos conta uma tentativa, avisa no Telegram e encerra a
    sessão ao atingir o limite. Em chamada manual (force) só devolve o status,
    sem contar tentativa nem spammar.
    """
    ESTADO["erro"] = motivo
    if force:
        return {"status": "sem_resultado", "data": d.isoformat(),
                "motivo": motivo}
    b = ESTADO["busca"]
    maxt = settings.busca_max_tentativas
    b["tentativas"] += 1
    n = b["tentativas"]
    telegram.enviar(_msg_tentativa(d, n, maxt, motivo))
    if n >= maxt:
        b["encerrada"] = True
        telegram.enviar(_msg_encerrada(d, maxt))
    if sheets.configurado():
        sheets.log_evento("busca", f"data={d} tentativa={n}/{maxt} {motivo}")
    return {"status": "aguardando_resultado", "data": d.isoformat(),
            "tentativa": n, "max": maxt, "encerrada": b["encerrada"]}


def run_check(force: bool = False, data_str: str | None = None) -> dict:
    """Entrada principal — chamada pelo scheduler (tick a cada 10 min) e pelo
    botão Atualizar.

    Nos dias de sorteio, dentro da janela `busca_hora_inicio`..`busca_hora_fim`,
    cada tick é uma tentativa: acha o resultado → processa e encerra; não acha →
    avisa no Telegram e agenda a próxima, até `busca_max_tentativas`.

    force=True (dashboard/manual) ignora dia, janela e limite de tentativas e
    aceita resultado de data diferente da esperada.
    """
    d = date.fromisoformat(data_str) if data_str else hoje_tz()
    eventos = eventos_na_data(d)
    todos = carregar_consorcios()
    alvos = [c for c in todos if any(e.consorcio_id == c.id for e in eventos)]
    if not alvos:
        if not force:
            return {"status": "sem_extracao_hoje", "data": d.isoformat()}
        alvos = todos

    b = _reset_busca(d)
    if not force:
        if b["resolvido"] or b["encerrada"]:
            return {"status": "busca_encerrada", "data": d.isoformat(),
                    "resolvido": b["resolvido"]}
        if not _dentro_janela(agora_tz()):
            return {"status": "fora_da_janela", "data": d.isoformat()}

    try:
        res = loteria.buscar_resultado(data_esperada=d)
    except loteria.LoteriaIndisponivel as exc:
        return _sem_resultado(d, f"API da Caixa indisponível: {exc}", force)

    if res.data != d and not force:
        return _sem_resultado(
            d, f"Última apuração disponível ainda é {_fmt_data(res.data)}.",
            force)

    resumo = _processar(res, alvos)
    b["resolvido"] = True
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

"""FastAPI: dashboard + endpoints de checagem."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import matching, service, sheets, telegram
from .config import carregar_consorcios, settings

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Consórcios Control", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.on_event("startup")
def _startup() -> None:
    service.carregar_estado_inicial()


def _exigir_secret(request: Request, secret: str | None) -> None:
    esperado = settings.cron_secret
    recebido = secret or request.headers.get("X-Cron-Secret")
    if not esperado or recebido != esperado:
        raise HTTPException(status_code=401, detail="secret inválido")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.api_route("/run-check", methods=["GET", "POST"])
def run_check(request: Request, secret: str | None = None,
              force: int = 0, date: str | None = None) -> JSONResponse:
    _exigir_secret(request, secret)
    try:
        return JSONResponse(service.run_check(force=bool(force), data_str=date))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/refresh")
def api_refresh() -> JSONResponse:
    """Botão 'Atualizar agora' do dashboard."""
    return JSONResponse(service.run_check(force=True))


@app.post("/manual-result")
def manual_result(data: str = Form(...), p1: str = Form(...), p2: str = Form(...),
                  p3: str = Form(...), p4: str = Form(...), p5: str = Form(...),
                  concurso: int = Form(0)) -> RedirectResponse:
    premios = [p.strip() for p in (p1, p2, p3, p4, p5)]
    if any(not p.isdigit() or len(p) != 5 for p in premios):
        raise HTTPException(status_code=400,
                            detail="Cada prêmio deve ter exatamente 5 dígitos.")
    service.registrar_manual(data, premios, concurso)
    return RedirectResponse(url="/", status_code=303)


@app.get("/calendario")
def calendario() -> JSONResponse:
    eventos = [e.model_dump(mode="json") for e in service.calendario()]
    return JSONResponse({"eventos": eventos})


DIAS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
           "sexta-feira", "sábado", "domingo"]


@app.get("/")
def dashboard(request: Request):
    consorcios = carregar_consorcios()
    res = service.ESTADO["resultado"]
    hoje = service.hoje_tz()

    # A extração pertence ao consórcio com evento na data do resultado.
    donos_ids = {e.consorcio_id for e in service.eventos_na_data(res.data)} if res else set()

    cards = []
    for cons in consorcios:
        analise = service.ESTADO["analises"].get(cons.id)
        prox = next((e.extracao for e in service.proximos_eventos(hoje, n=24)
                     if e.consorcio_id == cons.id), None)
        participou = not donos_ids or cons.id in donos_ids
        cards.append({"cons": cons, "analise": analise, "proxima": prox,
                      "participou": participou})
    cards.sort(key=lambda c: not c["participou"])

    donos = [c["cons"] for c in cards if c["cons"].id in donos_ids]
    ordem_destaque = None
    if donos:
        a = service.ESTADO["analises"].get(donos[0].id)
        if a and a.melhor:
            ordem_destaque = a.melhor.ordem

    # Redução do milhar do 1º prêmio ao espaço de cotas do grupo do Imóvel
    # (3.333), para a barra do número sorteado. None quando não há redução.
    milhar_reduzido = None
    if res:
        milhar_cons = next((c for c in consorcios if c.unidade == "milhar"), None)
        if milhar_cons:
            milhar_val = int(res.premios[0][-4:])
            cota = matching.para_espaco_cotas(milhar_val,
                                              milhar_cons.regra.como_regra())
            if cota is not None and cota != milhar_val:
                milhar_reduzido = cota

    cons_por_id = {c.id: c for c in consorcios}
    proximos_view = [{
        "evento": e,
        "cons": cons_por_id.get(e.consorcio_id),
        "dias": (e.extracao - hoje).days,
        "dia_semana": DIAS_PT[e.extracao.weekday()],
        "mes_nome": service.MESES_PT[e.extracao.month],
    } for e in service.proximos_eventos(hoje, n=5)]

    return templates.TemplateResponse(request, "dashboard.html", {
        "cards": cards,
        "resultado": res,
        "res_dia_semana": DIAS_PT[res.data.weekday()] if res else None,
        "donos": donos,
        "ordem_destaque": ordem_destaque,
        "proximos": proximos_view,
        "atualizado_em": service.ESTADO["atualizado_em"],
        "milhar_reduzido": milhar_reduzido,
        "erro": service.ESTADO["erro"],
        "sheets_ok": sheets.configurado(),
        "telegram_ok": telegram.configurado(),
        "hoje": hoje,
    })

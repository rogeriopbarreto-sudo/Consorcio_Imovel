"""FastAPI: dashboard + endpoints de checagem."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import service, sheets, telegram
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


@app.get("/")
def dashboard(request: Request):
    consorcios = carregar_consorcios()
    res = service.ESTADO["resultado"]
    hoje = service.hoje_tz()
    cards = []
    for cons in consorcios:
        analise = service.ESTADO["analises"].get(cons.id)
        prox = next((e.extracao for e in service.proximos_eventos(hoje, n=24)
                     if e.consorcio_id == cons.id), None)
        cards.append({"cons": cons, "analise": analise, "proxima": prox})
    return templates.TemplateResponse(request, "dashboard.html", {
        "cards": cards,
        "resultado": res,
        "proximos": service.proximos_eventos(hoje, n=4),
        "atualizado_em": service.ESTADO["atualizado_em"],
        "erro": service.ESTADO["erro"],
        "sheets_ok": sheets.configurado(),
        "telegram_ok": telegram.configurado(),
        "hoje": hoje,
    })

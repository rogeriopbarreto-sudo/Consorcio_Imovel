"""Cria as 6 abas da planilha com cabeçalhos e popula consorcios + calendario.

Uso (com .env preenchido na raiz do repo):
    python scripts/seed_sheets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import carregar_calendario_local, carregar_consorcios, settings  # noqa: E402
from app.sheets import ABAS  # noqa: E402


def main() -> None:
    if not (settings.google_service_account_json and settings.google_sheet_id):
        sys.exit("Configure GOOGLE_SERVICE_ACCOUNT_JSON e GOOGLE_SHEET_ID no .env")

    import gspread
    creds = json.loads(settings.google_service_account_json)
    client = gspread.service_account_from_dict(creds)
    planilha = client.open_by_key(settings.google_sheet_id)
    existentes = {ws.title for ws in planilha.worksheets()}

    for nome, colunas in ABAS.items():
        if nome in existentes:
            print(f"aba '{nome}' já existe — mantida")
            continue
        ws = planilha.add_worksheet(title=nome, rows=300, cols=len(colunas) + 2)
        ws.append_row(colunas)
        print(f"aba '{nome}' criada")

    ws = planilha.worksheet("consorcios")
    if len(ws.get_all_values()) <= 1:
        for c in carregar_consorcios():
            ws.append_row([c.id, c.nome, c.grupo, c.cota, c.unidade,
                           c.regra.model_dump_json()])
        print("aba 'consorcios' populada")

    ws = planilha.worksheet("calendario")
    if len(ws.get_all_values()) <= 1:
        linhas = []
        for e in carregar_calendario_local():
            linhas.append([
                e.consorcio_id,
                e.vencimento.isoformat() if e.vencimento else "",
                e.extracao.isoformat(),
                e.oferta_lance.isoformat() if e.oferta_lance else "",
                e.assembleia.isoformat() if e.assembleia else "",
                ";".join(d.isoformat() for d in e.chamadas),
            ])
        ws.append_rows(linhas)
        print(f"aba 'calendario' populada ({len(linhas)} eventos)")

    print("Seed concluído.")


if __name__ == "__main__":
    main()

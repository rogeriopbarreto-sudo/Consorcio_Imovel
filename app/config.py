"""Configuração: variáveis de ambiente + dados editáveis em data/*.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import Consorcio, EventoCalendario

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env",
                                      env_file_encoding="utf-8",
                                      extra="ignore")

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    google_service_account_json: str = ""
    google_sheet_id: str = ""
    cron_secret: str = ""
    app_timezone: str = "America/Sao_Paulo"

    # Janela de busca do resultado nos dias de sorteio (hora local BRT).
    # O app tenta a cada tick do scheduler enquanto hora ∈ [inicio, fim),
    # até achar o resultado ou esgotar `busca_max_tentativas`.
    busca_hora_inicio: int = 20
    busca_hora_fim: int = 22
    busca_max_tentativas: int = 10


settings = Settings()


@lru_cache
def carregar_consorcios() -> list[Consorcio]:
    raw = json.loads((DATA_DIR / "consorcios.json").read_text(encoding="utf-8"))
    return [Consorcio(**c) for c in raw]


@lru_cache
def carregar_calendario_local() -> list[EventoCalendario]:
    raw = json.loads((DATA_DIR / "calendario_2026.json").read_text(encoding="utf-8"))
    return [EventoCalendario(**e) for e in raw]


def consorcio_por_id(cid: str) -> Consorcio | None:
    return next((c for c in carregar_consorcios() if c.id == cid), None)

"""Modelos Pydantic compartilhados entre config, service e API."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from .matching import RegraGrupo


class RegraModel(BaseModel):
    digitos: int
    modulo: int
    base_um: bool
    equivalentes: list[int]
    elimina_zero: bool

    def como_regra(self) -> RegraGrupo:
        return RegraGrupo(
            digitos=self.digitos,
            modulo=self.modulo,
            base_um=self.base_um,
            equivalentes=tuple(self.equivalentes),
            elimina_zero=self.elimina_zero,
        )


class Consorcio(BaseModel):
    id: str
    nome: str
    emoji: str = ""
    administradora: str = "Ademicon"
    grupo: str
    cota: int
    unidade: str  # "milhar" ou "centena" (rótulo de exibição)
    regra: RegraModel


class ResultadoLoteria(BaseModel):
    concurso: int
    data: date
    premios: list[str]  # 5 bilhetes, na ordem 1º..5º
    origem: str = "caixa"  # "caixa" ou "manual"


class EventoCalendario(BaseModel):
    consorcio_id: str
    vencimento: date | None = None
    extracao: date
    oferta_lance: date | None = None
    assembleia: date | None = None
    chamadas: list[date] = []

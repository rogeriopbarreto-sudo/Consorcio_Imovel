"""Parsers das fontes da Loteria Federal (sem rede)."""
from datetime import date

import pytest

from app.loteria import _parse_caixa, _parse_espelho, _premios


def test_parse_caixa():
    dados = {
        "numero": 6073,
        "dataApuracao": "10/06/2026",
        "listaDezenas": ["24807", "62218", "87702", "74099", "08362"],
    }
    res = _parse_caixa(dados)
    assert res.concurso == 6073
    assert res.data == date(2026, 6, 10)
    assert res.premios == ["24807", "62218", "87702", "74099", "08362"]
    assert res.origem == "caixa"


def test_parse_espelho_normaliza_6_digitos():
    dados = {
        "concurso": 6073,
        "data": "10/06/2026",
        "dezenas": ["024807", "062218", "087702", "074099", "008362"],
    }
    res = _parse_espelho(dados)
    assert res.concurso == 6073
    assert res.data == date(2026, 6, 10)
    # 6 dígitos do espelho viram os mesmos 5 da fonte oficial
    assert res.premios == ["24807", "62218", "87702", "74099", "08362"]
    assert res.origem == "espelho"


def test_premios_preserva_zeros_a_esquerda():
    assert _premios(["00123", "045678", "11111", "22222", "33333"]) == \
        ["00123", "45678", "11111", "22222", "33333"]


def test_premios_lista_curta_falha():
    with pytest.raises(ValueError):
        _premios(["12345", "67890"])

"""Parsers e busca da Loteria Federal (sem rede)."""
from datetime import date

import pytest

from app import loteria
from app.loteria import _parse_caixa, _parse_espelho, _premios
from app.models import ResultadoLoteria


def _res(concurso, d):
    return ResultadoLoteria(concurso=concurso, data=d,
                            premios=["11111", "22222", "33333", "44444", "55555"],
                            origem="caixa")


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


def test_latest_bate_a_data_esperada(monkeypatch):
    monkeypatch.setattr(loteria, "_caixa",
                        lambda caminho="": _res(6081, date(2026, 7, 8)))
    res = loteria.buscar_resultado(data_esperada=date(2026, 7, 8))
    assert res.concurso == 6081


def test_sonda_proximo_concurso_quando_latest_atrasa(monkeypatch):
    # latest devolve 6080 (04/07); o esperado é 08/07, publicado só no 6081.
    def fake_caixa(caminho=""):
        if caminho == "":
            return _res(6080, date(2026, 7, 4))
        if caminho == "/6081":
            return _res(6081, date(2026, 7, 8))
        return None
    monkeypatch.setattr(loteria, "_caixa", fake_caixa)
    monkeypatch.setattr(loteria, "_get_json",
                        lambda url: (_ for _ in ()).throw(RuntimeError("sem espelho")))
    res = loteria.buscar_resultado(data_esperada=date(2026, 7, 8))
    assert res.concurso == 6081 and res.data == date(2026, 7, 8)


def test_sem_resultado_da_data_devolve_mais_recente(monkeypatch):
    # Nenhuma fonte tem 08/07 ainda; nem sondando (6081 inexistente → None).
    def fake_caixa(caminho=""):
        return _res(6080, date(2026, 7, 4)) if caminho == "" else None
    monkeypatch.setattr(loteria, "_caixa", fake_caixa)
    monkeypatch.setattr(loteria, "_get_json",
                        lambda url: (_ for _ in ()).throw(RuntimeError("sem espelho")))
    res = loteria.buscar_resultado(data_esperada=date(2026, 7, 8))
    assert res.data == date(2026, 7, 4)  # não inventa a data esperada

"""Ciclo de busca do dia: tentativas de 10 em 10 min, gate de janela/dia.

Congela hoje/agora e monkeypatcha a fonte da Loteria e o Telegram para
exercitar o service.run_check sem rede nem Sheets.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app import service
from app.models import ResultadoLoteria

TZ = ZoneInfo("America/Sao_Paulo")
DIA_SORTEIO = date(2026, 7, 8)          # extração do Veículo no calendário
DIA_SEM_SORTEIO = date(2026, 7, 9)
PREMIOS = ["53952", "58694", "08478", "31597", "64457"]


@pytest.fixture
def ambiente(monkeypatch):
    """Sem Sheets, Telegram capturado, relógio no dia de sorteio às 20:05."""
    enviadas: list[str] = []
    monkeypatch.setattr(service.telegram, "enviar",
                        lambda texto: enviadas.append(texto) or True)
    monkeypatch.setattr(service.telegram, "configurado", lambda: True)
    monkeypatch.setattr(service.sheets, "configurado", lambda: False)
    monkeypatch.setattr(service, "hoje_tz", lambda: DIA_SORTEIO)
    monkeypatch.setattr(service, "agora_tz",
                        lambda: datetime(2026, 7, 8, 20, 5, tzinfo=TZ))
    # zera a sessão de busca entre testes
    service.ESTADO["busca"] = {"data": None, "tentativas": 0,
                               "resolvido": False, "encerrada": False}
    return enviadas


def _resultado_defasado():
    return ResultadoLoteria(concurso=6070, data=date(2026, 7, 4),
                            premios=PREMIOS, origem="caixa")


def _resultado_do_dia():
    return ResultadoLoteria(concurso=6080, data=DIA_SORTEIO,
                            premios=PREMIOS, origem="caixa")


def test_nao_achou_conta_tentativa_e_avisa(ambiente, monkeypatch):
    monkeypatch.setattr(service.loteria, "buscar_resultado",
                        lambda data_esperada=None: _resultado_defasado())
    r = service.run_check()
    assert r["status"] == "aguardando_resultado"
    assert r["tentativa"] == 1 and r["max"] == 10
    assert len(ambiente) == 1
    assert "Tentativa <b>1/10</b>" in ambiente[0]


def test_para_em_dez_tentativas_com_aviso_final(ambiente, monkeypatch):
    monkeypatch.setattr(service.loteria, "buscar_resultado",
                        lambda data_esperada=None: _resultado_defasado())
    for _ in range(12):
        service.run_check()
    # 10 mensagens de tentativa + 1 de encerramento; ticks 11 e 12 são no-op
    assert len(ambiente) == 11
    assert "Tentativa <b>10/10</b>" in ambiente[9]
    assert "Encerrei a busca de hoje" in ambiente[10]
    assert service.ESTADO["busca"]["tentativas"] == 10
    r = service.run_check()
    assert r["status"] == "busca_encerrada"
    assert len(ambiente) == 11  # nenhuma mensagem nova


def test_achou_processa_e_encerra(ambiente, monkeypatch):
    monkeypatch.setattr(service.loteria, "buscar_resultado",
                        lambda data_esperada=None: _resultado_do_dia())
    r = service.run_check()
    assert r["status"] == "ok"
    assert service.ESTADO["busca"]["resolvido"] is True
    assert len(ambiente) == 1  # mensagem programada do Veículo
    # próximos ticks não repetem a mensagem
    r2 = service.run_check()
    assert r2["status"] == "busca_encerrada"
    assert len(ambiente) == 1


def test_fora_da_janela_nao_busca(ambiente, monkeypatch):
    monkeypatch.setattr(service, "agora_tz",
                        lambda: datetime(2026, 7, 8, 10, 0, tzinfo=TZ))

    def _nao_deve_chamar(data_esperada=None):
        raise AssertionError("não deveria buscar fora da janela")

    monkeypatch.setattr(service.loteria, "buscar_resultado", _nao_deve_chamar)
    r = service.run_check()
    assert r["status"] == "fora_da_janela"
    assert ambiente == []


def test_dia_sem_sorteio_noop(ambiente, monkeypatch):
    monkeypatch.setattr(service, "hoje_tz", lambda: DIA_SEM_SORTEIO)

    def _nao_deve_chamar(data_esperada=None):
        raise AssertionError("não deveria buscar em dia sem extração")

    monkeypatch.setattr(service.loteria, "buscar_resultado", _nao_deve_chamar)
    r = service.run_check()
    assert r["status"] == "sem_extracao_hoje"
    assert ambiente == []


def test_force_ignora_janela_e_data(ambiente, monkeypatch):
    monkeypatch.setattr(service, "agora_tz",
                        lambda: datetime(2026, 7, 8, 10, 0, tzinfo=TZ))
    monkeypatch.setattr(service.loteria, "buscar_resultado",
                        lambda data_esperada=None: _resultado_defasado())
    r = service.run_check(force=True)
    assert r["status"] == "ok"  # force aceita resultado de outra data

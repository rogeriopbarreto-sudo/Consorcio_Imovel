"""Linha do 1º prêmio na mensagem do Telegram (Imóvel e Veículo)."""
from app import matching, service
from app.config import consorcio_por_id

# Concurso 6075 (17/06/2026): 1º prêmio 53952
PREMIOS_6075 = ["53952", "58694", "08478", "31597", "64457"]


def test_linha_primeiro_premio_imovel():
    cons = consorcio_por_id("imovel")
    analise = matching.analisar(cons.cota, cons.regra.como_regra(), PREMIOS_6075)
    linha = service._linha_primeiro_premio(cons, analise)
    assert linha is not None
    assert linha.startswith("1º prêmio: 53952,")
    assert "milhar" in linha and "3952" in linha
    assert "cota <b>619</b>" in linha             # 3952 - 3333 = 619 (reduzido)
    assert "da sua cota <b>3311</b>" in linha
    assert "acima" in linha or "abaixo" in linha


def test_linha_primeiro_premio_veiculo():
    cons = consorcio_por_id("veiculo")
    analise = matching.analisar(cons.cota, cons.regra.como_regra(), PREMIOS_6075)
    linha = service._linha_primeiro_premio(cons, analise)
    assert linha is not None
    assert linha.startswith("1º prêmio: 53952,")
    assert "centena" in linha and "952" in linha
    assert "→ cota" not in linha                  # centena = cota, sem redução
    assert "da sua cota <b>974</b>" in linha

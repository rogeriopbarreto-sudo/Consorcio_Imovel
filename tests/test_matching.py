"""Testes da lógica pura de contemplação (app/matching.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.matching import (  # noqa: E402
    RegraGrupo,
    analisar,
    distancia_direcionada,
    extrair_numero,
    numeros_do_usuario,
    para_espaco_cotas,
)

IMOVEL = RegraGrupo(digitos=4, modulo=3333, base_um=True,
                    equivalentes=(0, 3333, 6666), elimina_zero=True)
VEICULO = RegraGrupo(digitos=3, modulo=1000, base_um=False,
                     equivalentes=(0,), elimina_zero=False)
COTA_IMOVEL = 3311
COTA_VEICULO = 974


# ---------- extração de número ----------

def test_extrair_milhar():
    assert extrair_numero("58694", 4) == "8694"
    assert extrair_numero("03317", 4) == "3317"
    assert extrair_numero("40005", 4) == "0005"


def test_extrair_centena():
    assert extrair_numero("58694", 3) == "694"
    assert extrair_numero("40000", 3) == "000"


def test_extrair_com_formatacao():
    assert extrair_numero("58.694", 4) == "8694"
    assert extrair_numero("123", 4) is None


# ---------- números do usuário ----------

def test_equivalentes_imovel():
    assert numeros_do_usuario(COTA_IMOVEL, IMOVEL) == [3311, 6644, 9977]


def test_veiculo_sem_equivalentes():
    assert numeros_do_usuario(COTA_VEICULO, VEICULO) == [974]


# ---------- mapeamento milhar → cota ----------

def test_milhar_para_cota():
    assert para_espaco_cotas(6644, IMOVEL) == 3311
    assert para_espaco_cotas(9977, IMOVEL) == 3311
    assert para_espaco_cotas(3311, IMOVEL) == 3311
    assert para_espaco_cotas(3334, IMOVEL) == 1
    assert para_espaco_cotas(9999, IMOVEL) == 3333


def test_milhar_zero_eliminada():
    assert para_espaco_cotas(0, IMOVEL) is None


def test_centena_zero_valida():
    assert para_espaco_cotas(0, VEICULO) == 0
    assert para_espaco_cotas(1000, VEICULO) == 0


# ---------- distância circular ----------

def test_distancia_direta_zero():
    assert distancia_direcionada(3311, 3311, IMOVEL) == (0, "acima")


def test_distancia_acima_abaixo():
    # sorteado 3315 está 4 acima da cota 3311
    assert distancia_direcionada(3311, 3315, IMOVEL) == (4, "acima")
    # sorteado 3307 está 4 abaixo
    assert distancia_direcionada(3311, 3307, IMOVEL) == (4, "abaixo")


def test_distancia_wrap_imovel():
    # de 3333 para 0001: 1 passo acima (wrap 3333 → 0001)
    assert distancia_direcionada(3333, 1, IMOVEL) == (1, "acima")
    # de 0001 para 3333: 1 passo abaixo (wrap 0001 → 3333)
    assert distancia_direcionada(1, 3333, IMOVEL) == (1, "abaixo")


def test_empate_prioriza_acima():
    # módulo 1000 (par): sorteado a exatamente 500 de distância nas duas direções
    assert distancia_direcionada(100, 600, VEICULO) == (500, "acima")


def test_distancia_wrap_veiculo():
    # 999 → 000: 1 acima no espaço circular 0..999
    assert distancia_direcionada(999, 0, VEICULO) == (1, "acima")


# ---------- análise completa: imóvel ----------

def test_match_direto_na_cota():
    premios = ["13311", "22222", "33333", "44444", "55555"]
    a = analisar(COTA_IMOVEL, IMOVEL, premios)
    assert a.contemplado is True
    assert a.ordem_contemplada == 1
    assert a.melhor.numero == "3311"


def test_match_no_equivalente():
    premios = ["11111", "26644", "33333", "44444", "55555"]
    a = analisar(COTA_IMOVEL, IMOVEL, premios)
    assert a.contemplado is True
    assert a.ordem_contemplada == 2
    assert a.melhor.numero == "6644"


def test_match_via_espaco_cotas():
    # milhar 9977 mapeia para cota 3311 (9977 - 6666)
    premios = ["19977", "22222", "33333", "44444", "55555"]
    a = analisar(COTA_IMOVEL, IMOVEL, premios)
    assert a.contemplado is True


def test_milhar_0000_eliminada_na_analise():
    premios = ["10000", "23311", "33333", "44444", "55555"]
    a = analisar(COTA_IMOVEL, IMOVEL, premios)
    assert a.premios[0].eliminado is True
    assert a.premios[0].distancia is None
    assert a.contemplado is True
    assert a.ordem_contemplada == 2


def test_sem_match_melhor_aproximacao():
    # cenário dos mockups: melhor é o 3º prêmio, milhar 6640, dist 4
    premios = ["58694", "03317", "96640", "11972", "40975"]
    a = analisar(COTA_IMOVEL, IMOVEL, premios)
    assert a.contemplado is False
    assert a.melhor.ordem == 3
    assert a.melhor.numero == "6640"
    assert a.melhor.distancia == 4
    assert a.melhor.direcao == "abaixo"  # 6640 está 4 abaixo de 6644
    assert a.melhor.numero_usuario == 6644


def test_empate_entre_premios_vence_menor_ordem():
    # 2º prêmio: 3315 (4 acima) e 4º prêmio: 3307 (4 abaixo) → vence o 2º
    premios = ["18694", "23315", "31972", "43307", "50975"]
    a = analisar(COTA_IMOVEL, IMOVEL, premios)
    assert a.melhor.ordem == 2
    assert a.melhor.distancia == 4


# ---------- análise completa: veículo ----------

def test_veiculo_match_direto():
    premios = ["11111", "22222", "33974", "44444", "55555"]
    a = analisar(COTA_VEICULO, VEICULO, premios)
    assert a.contemplado is True
    assert a.ordem_contemplada == 3
    assert a.melhor.numero == "974"


def test_veiculo_centena_000_concorre():
    premios = ["11000", "22222", "33333", "44444", "55555"]
    a = analisar(0, VEICULO, premios)
    assert a.contemplado is True
    assert a.ordem_contemplada == 1


def test_veiculo_proximidade():
    # cenário dos mockups: 5º prêmio centena 975, 1 acima da cota 974
    premios = ["58694", "03317", "96640", "11972", "40975"]
    a = analisar(COTA_VEICULO, VEICULO, premios)
    assert a.contemplado is False
    assert a.melhor.ordem == 5
    assert a.melhor.numero == "975"
    assert a.melhor.distancia == 1
    assert a.melhor.direcao == "acima"


def test_veiculo_ordem_dos_premios():
    # mesmo número em dois prêmios → vale o primeiro
    premios = ["11974", "22974", "33333", "44444", "55555"]
    a = analisar(COTA_VEICULO, VEICULO, premios)
    assert a.ordem_contemplada == 1

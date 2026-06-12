"""Lógica pura de contemplação — sem I/O, sem dependências externas.

Regras (fonte: Termo de Aditamento do grupo 000760 e Regulamento do grupo 01633):

Imóvel (milhar, espaço circular 1..3333):
- Milhar = últimos 4 dígitos de cada prêmio da Loteria Federal.
- Milhar 0000 é eliminada (passa ao próximo prêmio).
- Cada cota concorre com 3 números: cota, cota+3333, cota+6666.
- Milhar → cota: subtrair 3333 até cair em 1..3333.
- Wrap: acima de 3333 volta a 0001; abaixo de 0001 volta a 3333.

Veículo (centena, espaço circular 0..999):
- Centena = últimos 3 dígitos de cada prêmio.
- Centena 000 é válida (grupo de 1000 participantes), sem equivalentes.

Empate de distância nas duas direções → prioridade para a cota ACIMA.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegraGrupo:
    digitos: int                 # 4 (milhar) ou 3 (centena)
    modulo: int                  # 3333 (imóvel) ou 1000 (veículo)
    base_um: bool                # True: espaço 1..modulo; False: 0..modulo-1
    equivalentes: tuple[int, ...]  # offsets somados à cota (0, 3333, 6666) ou (0,)
    elimina_zero: bool           # True: número extraído 0000 é eliminado


@dataclass
class PremioAnalise:
    ordem: int                   # 1..5
    bilhete: str                 # bilhete completo sorteado
    numero: str | None           # milhar/centena extraída (string com zeros)
    eliminado: bool              # True quando milhar 0000 (imóvel)
    cota_sorteada: int | None    # número extraído mapeado no espaço de cotas
    numero_usuario: int | None   # número do usuário mais próximo (para exibição)
    distancia: int | None        # distância circular no espaço de cotas
    direcao: str | None          # "acima" ou "abaixo" (sorteado em relação à cota)


@dataclass
class Analise:
    contemplado: bool
    ordem_contemplada: int | None
    premios: list[PremioAnalise] = field(default_factory=list)
    melhor: PremioAnalise | None = None


def extrair_numero(premio: str, digitos: int) -> str | None:
    """Últimos N dígitos do bilhete premiado, preservando zeros à esquerda."""
    nums = re.sub(r"\D", "", str(premio))
    if len(nums) < digitos:
        return None
    return nums[-digitos:]


def numeros_do_usuario(cota: int, regra: RegraGrupo) -> list[int]:
    """Números com os quais a cota concorre (cota + equivalentes)."""
    return [cota + off for off in regra.equivalentes]


def para_espaco_cotas(valor: int, regra: RegraGrupo) -> int | None:
    """Mapeia o número extraído para o espaço de cotas do grupo.

    Imóvel: subtrai 3333 até cair em 1..3333 (0000 já eliminado antes).
    Veículo: módulo 1000 direto (000 é cota válida).
    """
    if regra.elimina_zero and valor == 0:
        return None
    if regra.base_um:
        v = valor
        while v > regra.modulo:
            v -= regra.modulo
        return v
    return valor % regra.modulo


def distancia_direcionada(cota_usuario: int, cota_sorteada: int,
                          regra: RegraGrupo) -> tuple[int, str]:
    """Distância circular mínima e direção do sorteado em relação à cota.

    Empate entre as duas direções → "acima" (prioridade da cota acima).
    """
    base = 1 if regra.base_um else 0
    a = (cota_sorteada - base) % regra.modulo
    b = (cota_usuario - base) % regra.modulo
    acima = (a - b) % regra.modulo
    abaixo = (b - a) % regra.modulo
    if acima <= abaixo:
        return acima, "acima"
    return abaixo, "abaixo"


def _equivalente_para_exibicao(extraido: int, cota: int, regra: RegraGrupo) -> int:
    """Escolhe o número do usuário (entre os equivalentes) mais próximo
    do valor extraído, apenas para exibição amigável no dashboard."""
    candidatos = numeros_do_usuario(cota, regra)
    return min(candidatos, key=lambda e: abs(extraido - e))


def analisar(cota: int, regra: RegraGrupo, premios: list[str]) -> Analise:
    """Analisa os 5 prêmios da Federal contra a cota do usuário.

    Retorna match direto (distância 0) ou a melhor aproximação
    (menor distância circular; empate entre prêmios → menor ordem).
    """
    linhas: list[PremioAnalise] = []
    for i, bilhete in enumerate(premios, start=1):
        numero = extrair_numero(bilhete, regra.digitos)
        if numero is None:
            linhas.append(PremioAnalise(i, str(bilhete), None, False,
                                        None, None, None, None))
            continue
        valor = int(numero)
        cota_sorteada = para_espaco_cotas(valor, regra)
        if cota_sorteada is None:  # milhar 0000 eliminada
            linhas.append(PremioAnalise(i, str(bilhete), numero, True,
                                        None, None, None, None))
            continue
        dist, direcao = distancia_direcionada(cota, cota_sorteada, regra)
        exibicao = _equivalente_para_exibicao(valor, cota, regra)
        linhas.append(PremioAnalise(i, str(bilhete), numero, False,
                                    cota_sorteada, exibicao, dist, direcao))

    validas = [l for l in linhas if l.distancia is not None]
    melhor = min(validas, key=lambda l: (l.distancia, l.ordem)) if validas else None
    contemplado = melhor is not None and melhor.distancia == 0
    ordem = melhor.ordem if contemplado else None
    return Analise(contemplado=contemplado, ordem_contemplada=ordem,
                   premios=linhas, melhor=melhor)

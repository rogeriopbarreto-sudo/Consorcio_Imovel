import requests
import pandas as pd
import streamlit as st
import plotly.express as px

URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api/federal"

MINHA_COTA = 3311
TOTAL_COTAS = 3333
ZONA_ALTA_CHANCE = 50


def buscar_resultado():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    dados = r.json()

    concurso = dados.get("numero")
    data = dados.get("dataApuracao")

    # Para a Federal, os 5 bilhetes vêm nesta lista.
    lista = dados.get("listaDezenas")

    if not isinstance(lista, list) or len(lista) == 0:
        # Mostra o JSON bruto para depuração caso a API mude no futuro
        raise Exception(f"Campo 'listaDezenas' ausente ou inválido. JSON recebido: {dados}")

    numero_primeiro_premio = str(lista[0]).strip()
    numero_primeiro_premio = "".join(ch for ch in numero_primeiro_premio if ch.isdigit())

    if len(numero_primeiro_premio) != 6:
        raise Exception(
            f"Formato inesperado para o 1º prêmio: '{numero_primeiro_premio}'. JSON recebido: {dados}"
        )

    return concurso, data, numero_primeiro_premio


def calcular_cota_contemplada(numero_bilhete, total_cotas=TOTAL_COTAS):
    # Usa o milhar (últimos 4 dígitos), conforme regra do grupo de 3.333
    milhar = int(numero_bilhete[-4:])

    while milhar > total_cotas:
        milhar -= total_cotas

    if milhar == 0:
        milhar = total_cotas

    return milhar


def distancia_circular(cota_a, cota_b, total_cotas=TOTAL_COTAS):
    # Grupo circular: acima de 3333 volta para 001
    direta = abs(cota_a - cota_b)
    circular = total_cotas - direta
    return min(direta, circular)


def classificar_chance(distancia, limite=ZONA_ALTA_CHANCE):
    return "ALTA CHANCE" if distancia <= limite else "BAIXA CHANCE"


def probabilidade_zona(limite=ZONA_ALTA_CHANCE, total_cotas=TOTAL_COTAS):
    # Zona: minha cota ± 50 => 101 cotas
    qtd = min(total_cotas, 2 * limite + 1)
    return qtd / total_cotas


st.set_page_config(
    page_title="Monitor de Consórcio Imobiliário - Rogerio Barreto",
    layout="centered"
)

st.markdown(
    "<h1 style='color:red;'>Monitor de Consórcio Imobiliário - Rogerio Barreto</h1>",
    unsafe_allow_html=True
)

try:
    concurso, data, numero = buscar_resultado()
    cota_contemplada = calcular_cota_contemplada(numero)
    distancia = distancia_circular(cota_contemplada, MINHA_COTA)
    chance = classificar_chance(distancia)
    prob_zona = probabilidade_zona()

    st.subheader("Resultado da Loteria Federal")
    st.write(f"**Concurso:** {concurso}")
    st.write(f"**Data do sorteio:** {data}")
    st.write(f"**Número sorteado (1º prêmio):** {numero}")
    st.write(f"**Cota contemplada:** {cota_contemplada:04d}")

    st.subheader("Comparação com a sua cota")
    st.write(f"**Minha cota:** {MINHA_COTA:04d}")
    st.write(f"**Cota Contemplada** {cota_contemplada:04d}")
    st.write(f"**Distância até a cota sorteada:** {distancia}")

    if chance == "ALTA CHANCE":
        st.success("Status: ALTA CHANCE")
    else:
        st.warning("Status: BAIXA CHANCE")

    st.subheader("Probabilidade")
    st.write(
        f"**Probabilidade de cair na zona de alta chance (±{ZONA_ALTA_CHANCE} cotas):** {prob_zona * 100:.2f}%"
    )
    st.caption("Isso mede a chance de o sorteio cair perto da sua cota, não a contemplação da sua cota exata.")

    df = pd.DataFrame(
        {
            "Item": ["Minha cota", "Cota sorteada"],
            "Cota": [MINHA_COTA, cota_contemplada],
        }
    )

    fig = px.bar(df, x="Item", y="Cota", text="Cota", title="Minha cota vs cota sorteada")
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis_title="Número da cota")
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:

    st.error(f"Erro ao obter resultado: {e}")

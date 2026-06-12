# Consórcios Control

Monitoramento automático dos consórcios Ademicon (Imóvel — grupo 000760, cota 3311; Veículo — grupo 01633, cota 974). Nas datas de extração, o app busca o resultado da Loteria Federal na API oficial da Caixa, aplica a regra de contemplação de cada grupo, grava tudo em Google Sheets, mostra num dashboard e avisa por Telegram.

> ⚠️ **Aviso**: o app faz uma **análise matemática** baseada nos regulamentos dos grupos. Não é confirmação oficial — a palavra final é sempre da Ademicon.

## Como funciona

- **Imóvel (milhar)**: últimos 4 dígitos de cada prêmio, do 1º ao 5º. Milhar `0000` é eliminada. A cota concorre com 3 números: 3311, 6644 e 9977. Espaço circular 1..3333 (acima de 3333 volta a 0001).
- **Veículo (centena)**: últimos 3 dígitos de cada prêmio. Centena `000` é válida (grupo de 1000 cotas). Espaço circular 0..999.
- Sem match direto, o app calcula a distância circular mínima e a direção (acima/abaixo; empate → acima).

Tudo é editável: regras em `data/consorcios.json`, calendário em `data/calendario_2026.json` e na aba `calendario` da planilha (a planilha tem prioridade).

## Setup

### 1. Google Sheets

1. Crie uma planilha no Google Sheets e copie o ID da URL.
2. No [Google Cloud Console](https://console.cloud.google.com), crie um projeto, ative a API do Google Sheets e do Google Drive, e crie uma **service account**. Baixe a chave JSON.
3. Compartilhe a planilha com o e-mail da service account (permissão de editor).
4. Preencha `GOOGLE_SERVICE_ACCOUNT_JSON` (o JSON em uma linha) e `GOOGLE_SHEET_ID` no `.env`.
5. Rode `python scripts/seed_sheets.py` — cria as 6 abas (`consorcios`, `calendario`, `resultados`, `analises`, `notificacoes`, `log`) e popula consórcios + calendário.

### 2. Telegram

1. Fale com o [@BotFather](https://t.me/BotFather), crie um bot e copie o token.
2. Envie uma mensagem qualquer para o bot, depois abra `https://api.telegram.org/bot<TOKEN>/getUpdates` e copie o `chat.id`.
3. Preencha `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`.

### 3. Deploy no Render

1. Conecte este repositório no [Render](https://render.com) — o `render.yaml` configura tudo (free tier).
2. Preencha as variáveis de ambiente no painel (as mesmas do `.env.example`).
3. O serviço sobe com `uvicorn app.main:app`.

### 4. Cron externo

O free tier do Render hiberna; use um cron externo (ex.: [cron-job.org](https://cron-job.org)) chamando:

```
GET https://SEU-APP.onrender.com/run-check?secret=SEU_CRON_SECRET
```

diariamente às **19h, 20h, 21h, 22h e 23h** (America/Sao_Paulo). Fora das datas de extração a resposta é `{"status": "sem_extracao_hoje"}` e nada acontece. As notificações têm dedup por (data, consórcio): chamadas repetidas não geram mensagem duplicada.

## Testes manuais

- `pytest` — roda os testes da lógica de contemplação.
- `GET /run-check?secret=...&force=1&date=2026-06-17` — força a checagem para uma data.
- Dashboard → botão **Atualizar agora** ou formulário de **input manual** (fallback quando a API da Caixa falha).
- Confira as abas `resultados`/`analises` na planilha e a mensagem no Telegram.

## Rotas

| Rota | Descrição |
| :--- | :--- |
| `GET /` | Dashboard |
| `GET/POST /run-check?secret=&force=&date=` | Pipeline completo (cron) — exige `CRON_SECRET` |
| `POST /api/refresh` | Atualização manual via dashboard |
| `POST /manual-result` | Input manual dos 5 prêmios |
| `GET /calendario` | Calendário em JSON |
| `GET /healthz` | Health check |

## Quando você estiver no seu computador de casa

```powershell
git clone https://github.com/rogeriopbarreto-sudo/Consorcio_Imovel.git
cd Consorcio_Imovel
copy .env.example .env   # e preencha
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

Abra http://127.0.0.1:8000. Documentos sensíveis (contratos, PDFs) ficam em `docs_local/` — pasta ignorada pelo git, nunca commitada.

## Premissas documentadas

- Calendários 2026 extraídos dos boletos/regulamentos (editáveis na aba `calendario`).
- Regra do imóvel: Termo de Aditamento do grupo 000760 (p. 3 do contrato).
- Regra do veículo: Regulamento do grupo 01633, cláusulas 45–46.
- Nenhum dado pessoal (CPF, endereço, telefone) vive no código — só grupo, cota e regras.

# ⚡ Realtime Analytics API

API de **análise de dados em tempo real** feita com FastAPI. Recebe métricas por HTTP ou WebSocket, analisa tudo na hora (estatísticas, anomalias, tendência), dispara alertas e transmite os resultados ao vivo.

## Recursos

| Área | O que tem |
|---|---|
| **Ingestão** | `POST /ingest`, `POST /ingest/batch` (até 1000 pontos), WebSocket `/ws/ingest` |
| **Análise** | estatísticas (média, desvio, percentis p25–p99), EWMA, tendência (regressão linear + R²), agregação por intervalo, correlação de Pearson |
| **Anomalias** | z-score, IQR (Tukey) e MAD (robusto) — em lote e **a cada ponto que chega** |
| **Previsão** | Holt (suavização exponencial dupla) com banda de confiança de 95% |
| **Alertas** | regras de limiar (`gt/gte/lt/lte/eq`) ou de anomalia, por métrica ou `*`, com cooldown e histórico |
| **Tempo real** | WebSocket `/ws/metrics/{metric}` (use `*` para tudo) e Server-Sent Events |
| **Segurança** | JWT, senhas com PBKDF2-SHA256 + salt, rate limit por IP, validação estrita (Pydantic) |
| **Operação** | SQLite (WAL) para persistência, ring buffer em memória, retenção automática, `/health`, `/prometheus`, Docker, CI |
| **Extras** | dashboard ao vivo em `/`, export CSV, simulador de dados, 32 testes |

## Rodando

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # ajuste SECRET_KEY!
uvicorn app.main:app --reload
```

- Dashboard: http://localhost:8000
- Swagger: http://localhost:8000/docs

Gerar dados fake (outro terminal):

```bash
python scripts/simulator.py --url http://localhost:8000
```

Docker: `docker compose up --build`

## Exemplo rápido

```bash
# criar conta e logar
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"joao","password":"senha12345"}'
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"joao","password":"senha12345"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# enviar ponto
curl -X POST localhost:8000/api/v1/ingest -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"metric":"cpu.usage","value":42.5,"tags":{"host":"srv-01"}}'

# analisar
curl localhost:8000/api/v1/metrics/cpu.usage/stats -H "Authorization: Bearer $TOKEN"
curl "localhost:8000/api/v1/metrics/cpu.usage/anomalies?method=mad" -H "Authorization: Bearer $TOKEN"
curl "localhost:8000/api/v1/metrics/cpu.usage/forecast?steps=10" -H "Authorization: Bearer $TOKEN"

# criar alerta
curl -X POST localhost:8000/api/v1/alerts -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"metric":"cpu.usage","kind":"threshold","op":"gt","threshold":90}'
```

### WebSocket (Python)

```python
import asyncio, json, websockets

async def main():
    async with websockets.connect(f"ws://localhost:8000/ws/metrics/cpu.usage?token={TOKEN}") as ws:
        async for msg in ws:
            ev = json.loads(msg)          # type: snapshot | point | alert
            print(ev["type"], ev.get("value"), ev.get("anomaly"))

asyncio.run(main())
```

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/v1/auth/register` · `/login` | cria conta · gera JWT |
| GET | `/api/v1/auth/me` | usuário atual |
| POST | `/api/v1/ingest` · `/ingest/batch` | ingestão |
| GET | `/api/v1/metrics` | lista métricas ativas |
| GET | `/api/v1/metrics/{m}/series` | série bruta |
| GET | `/api/v1/metrics/{m}/stats` | estatísticas + EWMA + tendência |
| GET | `/api/v1/metrics/{m}/aggregate?interval=60` | agregação por janela |
| GET | `/api/v1/metrics/{m}/anomalies?method=zscore\|iqr\|mad` | anomalias |
| GET | `/api/v1/metrics/{m}/forecast?steps=10` | previsão |
| GET | `/api/v1/metrics/{m}/export.csv` | exporta CSV |
| DELETE | `/api/v1/metrics/{m}` | apaga métrica |
| GET | `/api/v1/correlation?a=&b=` | correlação entre métricas |
| POST/GET/DELETE | `/api/v1/alerts` · `/alerts/{id}` | regras |
| GET | `/api/v1/alerts/events` | alertas disparados |
| GET | `/api/v1/stream/{m}?token=` | SSE |
| WS | `/ws/metrics/{m}?token=` · `/ws/ingest?token=` | tempo real |
| GET | `/health` · `/prometheus` | operação |

## Configuração (`.env`)

| Variável | Padrão | Descrição |
|---|---|---|
| `SECRET_KEY` | (dev) | **troque em produção** (32+ caracteres) |
| `TOKEN_EXPIRE_MINUTES` | 60 | validade do JWT |
| `DB_PATH` | data/analytics.db | arquivo SQLite |
| `BUFFER_SIZE` | 5000 | pontos por métrica mantidos em memória |
| `RETENTION_DAYS` | 30 | retenção no banco |
| `RATE_LIMIT_PER_MINUTE` | 600 | por IP (0 desliga) |
| `ALLOW_REGISTRATION` | true | liberar cadastro público |
| `ADMIN_USER` / `ADMIN_PASSWORD` | vazio | cria um usuário no startup |
| `CORS_ORIGINS` | * | origens separadas por vírgula |

## Arquitetura

```
cliente ──HTTP/WS──► routers ──► pipeline ──► hub (ring buffer + pub/sub) ──► WebSocket / SSE
                                    │  ├─► detecção de anomalia (z-score)
                                    │  ├─► motor de alertas (regras + cooldown)
                                    │  └─► SQLite (persistência + retenção)
                                    └─► análises sob demanda (numpy): stats, trend, forecast, correlação
```

As consultas analíticas rodam sobre o buffer em memória (últimos `BUFFER_SIZE` pontos por métrica), que é recarregado do SQLite ao reiniciar.

## Testes

```bash
pytest -q
```

## Ideias de evolução

Redis pub/sub para escalar em várias instâncias · TimescaleDB/InfluxDB no lugar do SQLite · métricas por usuário (multi-tenant) · webhooks/e-mail/Telegram nos alertas · sazonalidade (Holt-Winters).

## Licença

MIT

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import settings
from .routers import alerts, auth, data, stream, system
from .state import state

DESCRIPTION = """
API de **análise de dados em tempo real**: ingestão por HTTP/WebSocket, estatísticas em janela,
detecção de anomalias (z-score, IQR, MAD), previsão (Holt), correlação, alertas com regras,
streaming via WebSocket/SSE e métricas Prometheus.

Dashboard ao vivo em [`/`](/). Autentique com `POST /api/v1/auth/login` e use o botão **Authorize**.
"""


async def _retention_loop():
    while True:
        await asyncio.sleep(3600)
        cutoff = time.time() - settings.retention_days * 86400
        await asyncio.to_thread(state.db.purge_older_than, cutoff)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.start()
    task = asyncio.create_task(_retention_loop())
    yield
    task.cancel()
    state.stop()


app = FastAPI(title=settings.app_name, version=settings.version, description=DESCRIPTION, lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

_hits = defaultdict(deque)
_OPEN_PATHS = ("/health", "/docs", "/openapi.json", "/redoc", "/")


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path in _OPEN_PATHS or settings.rate_limit_per_minute <= 0:
        return await call_next(request)
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_minute:
        retry = max(1, int(60 - (now - q[0])))
        return JSONResponse({"detail": "Limite de requisições excedido"}, status_code=429,
                            headers={"Retry-After": str(retry)})
    q.append(now)
    return await call_next(request)


app.include_router(system.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(data.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(stream.router)

_DASH = Path(__file__).parent / "static" / "dashboard.html"


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(_DASH)

import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..state import state

router = APIRouter(tags=["Sistema"])


@router.get("/health", summary="Healthcheck")
def health():
    return {
        "status": "ok" if state.db.ping() else "degraded",
        "version": settings.version,
        "uptime_seconds": round(time.time() - state.started_at, 1),
        "metrics_active": len(state.hub.metrics()),
        "websocket_connections": state.ws_connections,
        **state.counters,
    }


@router.get("/prometheus", response_class=PlainTextResponse, summary="Métricas no formato Prometheus")
def prometheus():
    c = state.counters
    lines = [
        "# TYPE rtapi_points_ingested_total counter", f"rtapi_points_ingested_total {c['points_ingested']}",
        "# TYPE rtapi_anomalies_total counter", f"rtapi_anomalies_total {c['anomalies']}",
        "# TYPE rtapi_alerts_fired_total counter", f"rtapi_alerts_fired_total {c['alerts_fired']}",
        "# TYPE rtapi_ws_connections gauge", f"rtapi_ws_connections {state.ws_connections}",
        "# TYPE rtapi_uptime_seconds gauge", f"rtapi_uptime_seconds {time.time() - state.started_at:.1f}",
        "# TYPE rtapi_metric_last_value gauge",
    ]
    for m in state.hub.metrics():
        lines.append(f'rtapi_metric_last_value{{metric="{m}"}} {state.hub.last(m)[1]}')
    return "\n".join(lines) + "\n"

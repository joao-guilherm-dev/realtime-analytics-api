import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..analytics import anomaly as anom
from ..analytics import engine
from ..analytics.forecast import holt_forecast
from ..pipeline import process_points
from ..schemas import IngestBatch, IngestPoint
from ..security import current_user
from ..state import state

router = APIRouter(dependencies=[Depends(current_user)])


def _load(metric: str, limit: Optional[int], seconds: Optional[int]):
    if not state.hub.has(metric):
        raise HTTPException(404, f"Métrica '{metric}' não encontrada")
    since = time.time() - seconds if seconds else None
    ts, vals = state.hub.arrays(metric, limit=limit, since=since)
    if vals.size == 0:
        raise HTTPException(404, "Sem dados na janela solicitada")
    return ts, vals


# ------------------------------------------------------------------ ingestão
@router.post("/ingest", status_code=201, tags=["Ingestão"], summary="Envia um ponto")
async def ingest(point: IngestPoint):
    events, fired = await process_points([point])
    return {**events[0], "alerts_fired": fired}


@router.post("/ingest/batch", status_code=201, tags=["Ingestão"], summary="Envia até 1000 pontos de uma vez")
async def ingest_batch(batch: IngestBatch):
    events, fired = await process_points(batch.points)
    return {
        "accepted": len(events),
        "anomalies": sum(1 for e in events if e["anomaly"]),
        "alerts_fired": fired,
    }


# ------------------------------------------------------------------ consulta
@router.get("/metrics", tags=["Métricas & Análises"], summary="Lista métricas ativas")
def list_metrics():
    out = []
    for m in state.hub.metrics():
        ts, v = state.hub.last(m)
        out.append({"metric": m, "points_in_buffer": state.hub.size(m), "last_ts": ts, "last_value": v})
    return {"count": len(out), "metrics": out}


@router.get("/metrics/{metric}/series", tags=["Métricas & Análises"], summary="Série temporal bruta")
def series(metric: str, limit: int = Query(200, ge=1, le=10000), seconds: Optional[int] = Query(None, ge=1)):
    ts, vals = _load(metric, limit, seconds)
    return {"metric": metric, "count": int(vals.size),
            "points": [{"ts": float(t), "value": float(v)} for t, v in zip(ts, vals)]}


@router.get("/metrics/{metric}/stats", tags=["Métricas & Análises"],
            summary="Estatísticas, EWMA, tendência e taxa de chegada")
def stats(metric: str, limit: Optional[int] = Query(1000, ge=1, le=10000),
          seconds: Optional[int] = Query(None, ge=1), alpha: float = Query(0.3, gt=0, le=1)):
    ts, vals = _load(metric, limit, seconds)
    duration = float(ts[-1] - ts[0])
    return {
        "metric": metric,
        "window": {"points": int(vals.size), "from": float(ts[0]), "to": float(ts[-1]), "duration_seconds": duration},
        "stats": engine.describe(vals),
        "ewma": engine.ewma(vals, alpha)[-1],
        "trend": engine.linear_trend(ts, vals),
        "rate_per_second": float(vals.size / duration) if duration > 0 else None,
        "last": {"ts": float(ts[-1]), "value": float(vals[-1])},
    }


@router.get("/metrics/{metric}/aggregate", tags=["Métricas & Análises"], summary="Agregação por intervalo de tempo")
def aggregate(metric: str, interval: int = Query(60, ge=1, le=86400),
              seconds: Optional[int] = Query(3600, ge=1)):
    ts, vals = _load(metric, None, seconds)
    buckets = engine.aggregate(ts, vals, interval)
    return {"metric": metric, "interval_seconds": interval, "buckets": buckets}


@router.get("/metrics/{metric}/anomalies", tags=["Métricas & Análises"], summary="Detecta anomalias na janela")
def anomalies(metric: str, method: Literal["zscore", "iqr", "mad"] = "zscore",
              threshold: Optional[float] = Query(None, gt=0), limit: int = Query(1000, ge=3, le=10000),
              seconds: Optional[int] = Query(None, ge=1)):
    ts, vals = _load(metric, limit, seconds)
    flags, scores = anom.detect(vals, method, threshold)
    found = [{"ts": float(ts[i]), "value": float(vals[i]), "score": float(scores[i])}
             for i in range(vals.size) if flags[i]]
    return {
        "metric": metric, "method": method,
        "threshold": anom.DEFAULTS[method] if threshold is None else threshold,
        "analyzed": int(vals.size), "anomaly_count": len(found),
        "anomaly_rate": len(found) / vals.size, "anomalies": found,
    }


@router.get("/metrics/{metric}/forecast", tags=["Métricas & Análises"], summary="Previsão (Holt) com banda de confiança")
def forecast(metric: str, steps: int = Query(10, ge=1, le=200), limit: int = Query(500, ge=3, le=10000),
             alpha: float = Query(0.5, gt=0, le=1), beta: float = Query(0.3, gt=0, le=1)):
    ts, vals = _load(metric, limit, None)
    try:
        result = holt_forecast(ts, vals, steps, alpha, beta)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"metric": metric, "based_on_points": int(vals.size), **result}


@router.get("/metrics/{metric}/export.csv", tags=["Métricas & Análises"], summary="Exporta a série em CSV")
def export_csv(metric: str, limit: int = Query(10000, ge=1, le=100000)):
    ts, vals = _load(metric, limit, None)

    def gen():
        yield "timestamp,value\n"
        for t, v in zip(ts, vals):
            yield f"{t:.6f},{v}\n"

    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{metric}.csv"'})


@router.delete("/metrics/{metric}", tags=["Métricas & Análises"], summary="Apaga a métrica (buffer + banco)")
def delete_metric(metric: str):
    if not state.hub.has(metric):
        raise HTTPException(404, f"Métrica '{metric}' não encontrada")
    state.hub.delete(metric)
    return {"metric": metric, "deleted_points": state.db.delete_metric(metric)}


@router.get("/correlation", tags=["Métricas & Análises"], summary="Correlação de Pearson entre duas métricas")
def correlation(a: str, b: str, interval: int = Query(10, ge=1, le=86400),
                seconds: Optional[int] = Query(3600, ge=1)):
    ta, va = _load(a, None, seconds)
    tb, vb = _load(b, None, seconds)
    res = engine.correlation(ta, va, tb, vb, interval)
    if res is None:
        raise HTTPException(422, "Dados insuficientes ou sem variação (mín. 3 intervalos em comum)")
    r, n = res
    return {"a": a, "b": b, "interval_seconds": interval, "common_buckets": n,
            "pearson": r, "interpretation": engine.interpret_correlation(r)}

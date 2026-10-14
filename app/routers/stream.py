import asyncio
import json

import jwt
from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from ..analytics.engine import describe
from ..pipeline import process_points
from ..schemas import IngestPoint
from ..security import current_user_flex, decode_token
from ..state import state

router = APIRouter()


async def _auth(ws: WebSocket, token: str) -> bool:
    try:
        decode_token(token)
        return True
    except jwt.PyJWTError:
        await ws.close(code=4401)
        return False


@router.websocket("/ws/metrics/{metric}")
async def ws_metric(ws: WebSocket, metric: str, token: str = Query(default="")):
    """Assina uma métrica em tempo real (use '*' para todas). Auth: ?token=JWT"""
    if not await _auth(ws, token):
        return
    await ws.accept()
    state.ws_connections += 1
    q = state.hub.subscribe(metric)
    try:
        ts, vals = state.hub.arrays(metric, limit=120)
        await ws.send_json({
            "type": "snapshot", "metric": metric,
            "series": [[float(t), float(v)] for t, v in zip(ts, vals)],
            "stats": describe(vals),
        })
        while True:
            await ws.send_json(await q.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        state.hub.unsubscribe(metric, q)
        state.ws_connections -= 1


@router.websocket("/ws/ingest")
async def ws_ingest(ws: WebSocket, token: str = Query(default="")):
    """Ingestão por WebSocket: envie um ponto ou uma lista de pontos em JSON."""
    if not await _auth(ws, token):
        return
    await ws.accept()
    state.ws_connections += 1
    try:
        while True:
            data = await ws.receive_json()
            items = data if isinstance(data, list) else [data]
            if len(items) > 1000:
                await ws.send_json({"type": "error", "detail": "máximo de 1000 pontos por mensagem"})
                continue
            try:
                points = [IngestPoint.model_validate(i) for i in items]
            except ValidationError as e:
                await ws.send_json({"type": "error", "detail": json.loads(e.json())})
                continue
            events, fired = await process_points(points)
            await ws.send_json({"type": "ack", "accepted": len(events),
                                "anomalies": sum(1 for e in events if e["anomaly"]), "alerts_fired": fired})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        state.ws_connections -= 1


@router.get("/api/v1/stream/{metric}", tags=["Tempo real"], summary="Server-Sent Events de uma métrica")
async def sse(metric: str, request: Request, _: str = Depends(current_user_flex)):
    q = state.hub.subscribe(metric)

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
        finally:
            state.hub.unsubscribe(metric, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

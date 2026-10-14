"""Pipeline de ingestão: detecta anomalia, atualiza buffer, publica eventos, avalia alertas e persiste."""
import asyncio
import json
import time
from typing import Dict, List, Tuple

import numpy as np

from .alerts import MIN_HISTORY
from .analytics.anomaly import score_point
from .schemas import IngestPoint
from .state import state

ANOMALY_WINDOW = 100


def _persist(rows, alert_events) -> List[int]:
    state.db.insert_points(rows)
    return state.db.insert_events(alert_events)


async def process_points(points: List[IngestPoint]) -> Tuple[List[Dict], int]:
    hub = state.hub
    rows, fired_all, events = [], [], []
    for p in points:
        ts = p.timestamp if p.timestamp is not None else time.time()
        hist = hub.recent_values(p.metric, ANOMALY_WINDOW)
        if len(hist) >= MIN_HISTORY:
            is_anom, score = score_point(hist, p.value, "zscore")
        else:
            is_anom, score = False, 0.0
        hub.add(p.metric, ts, p.value)
        rows.append((p.metric, ts, p.value, json.dumps(p.tags)))

        win = np.asarray(hist[-50:] + [p.value])
        event = {
            "type": "point", "metric": p.metric, "ts": ts, "value": p.value, "tags": p.tags,
            "anomaly": is_anom, "score": round(score, 4),
            "window": {"n": int(win.size), "mean": float(win.mean()),
                       "std": float(win.std(ddof=1)) if win.size > 1 else 0.0},
        }
        events.append(event)
        hub.publish(p.metric, event)
        fired_all.extend(state.alerts.evaluate(p.metric, p.value, ts, hist))

    ids = await asyncio.to_thread(_persist, rows, fired_all)
    for fid, f in zip(ids, fired_all):
        hub.publish(f["metric"], {"type": "alert", "id": fid, **f})

    state.counters["points_ingested"] += len(points)
    state.counters["anomalies"] += sum(1 for e in events if e["anomaly"])
    state.counters["alerts_fired"] += len(fired_all)
    return events, len(fired_all)

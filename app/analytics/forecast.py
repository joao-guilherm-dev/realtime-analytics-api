"""Previsão de curto prazo com suavização exponencial dupla (Holt)."""
from typing import Dict, List

import numpy as np


def holt_forecast(ts, values, steps: int = 10, alpha: float = 0.5, beta: float = 0.3) -> Dict[str, object]:
    t = np.asarray(ts, dtype=float)
    y = np.asarray(values, dtype=float)
    if y.size < 3:
        raise ValueError("São necessários ao menos 3 pontos para prever")
    level = y[0]
    trend = y[1] - y[0]
    errors: List[float] = []
    for v in y[1:]:
        errors.append(v - (level + trend))
        prev = level
        level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
    sigma = float(np.std(errors, ddof=1)) if len(errors) > 1 else 0.0
    dt = float(np.median(np.diff(t))) if t.size > 1 else 1.0
    if dt <= 0:
        dt = 1.0
    points = []
    for i in range(1, steps + 1):
        mean = float(level + i * trend)
        band = 1.96 * sigma * float(np.sqrt(i))
        points.append({
            "ts": float(t[-1] + i * dt),
            "forecast": mean,
            "lower": mean - band,
            "upper": mean + band,
        })
    return {"step_seconds": dt, "residual_std": sigma, "alpha": alpha, "beta": beta, "points": points}

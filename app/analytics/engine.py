"""Estatísticas descritivas, tendência, agregação por janela e correlação (numpy)."""
from typing import Dict, List, Optional

import numpy as np


def describe(values) -> Dict[str, float]:
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return {"count": 0}
    p25, p50, p75, p90, p95, p99 = np.percentile(a, [25, 50, 75, 90, 95, 99])
    return {
        "count": int(a.size),
        "sum": float(a.sum()),
        "mean": float(a.mean()),
        "std": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "min": float(a.min()),
        "max": float(a.max()),
        "median": float(p50),
        "p25": float(p25),
        "p75": float(p75),
        "p90": float(p90),
        "p95": float(p95),
        "p99": float(p99),
    }


def ewma(values, alpha: float = 0.3) -> List[float]:
    out: List[float] = []
    s: Optional[float] = None
    for v in values:
        s = float(v) if s is None else alpha * float(v) + (1 - alpha) * s
        out.append(s)
    return out


def linear_trend(ts, values) -> Optional[Dict[str, object]]:
    t = np.asarray(ts, dtype=float)
    y = np.asarray(values, dtype=float)
    if t.size < 3 or np.ptp(t) == 0:
        return None
    x = t - t[0]
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    if r2 < 0.05:
        direction = "estavel"
    else:
        direction = "alta" if slope > 0 else "queda"
    return {
        "slope_per_second": float(slope),
        "intercept": float(intercept),
        "r2": float(r2),
        "direction": direction,
    }


def aggregate(ts, values, interval: int) -> List[Dict[str, float]]:
    t = np.asarray(ts, dtype=float)
    v = np.asarray(values, dtype=float)
    if t.size == 0:
        return []
    buckets = np.floor(t / interval).astype(np.int64)
    uniq, inv = np.unique(buckets, return_inverse=True)
    inv = inv.reshape(-1)
    out = []
    for i, b in enumerate(uniq):
        seg = v[inv == i]
        out.append({
            "start": float(b * interval),
            "count": int(seg.size),
            "mean": float(seg.mean()),
            "min": float(seg.min()),
            "max": float(seg.max()),
            "sum": float(seg.sum()),
        })
    return out


def _bucket_means(ts, values, interval: int) -> Dict[int, float]:
    t = np.asarray(ts, dtype=float)
    v = np.asarray(values, dtype=float)
    b = np.floor(t / interval).astype(np.int64)
    uniq, inv = np.unique(b, return_inverse=True)
    inv = inv.reshape(-1)
    sums = np.bincount(inv, weights=v)
    counts = np.bincount(inv)
    return dict(zip(uniq.tolist(), (sums / counts).tolist()))


def correlation(ts_a, va, ts_b, vb, interval: int):
    """Pearson sobre as médias por bucket de tempo. Retorna (r, n_buckets) ou None."""
    ma = _bucket_means(ts_a, va, interval)
    mb = _bucket_means(ts_b, vb, interval)
    common = sorted(set(ma) & set(mb))
    if len(common) < 3:
        return None
    xa = np.array([ma[k] for k in common])
    xb = np.array([mb[k] for k in common])
    if xa.std() == 0 or xb.std() == 0:
        return None
    return float(np.corrcoef(xa, xb)[0, 1]), len(common)


def interpret_correlation(r: float) -> str:
    mag = abs(r)
    if mag >= 0.7:
        força = "forte"
    elif mag >= 0.4:
        força = "moderada"
    elif mag >= 0.2:
        força = "fraca"
    else:
        return "correlação desprezível"
    return f"correlação {força} {'positiva' if r > 0 else 'negativa'}"

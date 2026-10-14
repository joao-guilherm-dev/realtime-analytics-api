"""Detecção de anomalias: z-score, IQR (Tukey) e MAD (z-score robusto)."""
from typing import Optional, Tuple

import numpy as np

DEFAULTS = {"zscore": 3.0, "iqr": 1.5, "mad": 3.5}
CAP = 999.0  # evita inf no JSON


def _thr(method: str, threshold: Optional[float]) -> float:
    if method not in DEFAULTS:
        raise ValueError(f"método inválido: {method}")
    return DEFAULTS[method] if threshold is None else float(threshold)


def detect(values, method: str = "zscore", threshold: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Analisa a série inteira. Retorna (flags, scores)."""
    a = np.asarray(values, dtype=float)
    thr = _thr(method, threshold)
    if a.size < 3:
        return np.zeros(a.size, dtype=bool), np.zeros(a.size)
    if method == "zscore":
        std = a.std(ddof=1)
        scores = np.zeros(a.size) if std == 0 else (a - a.mean()) / std
        return np.abs(scores) > thr, np.clip(scores, -CAP, CAP)
    if method == "mad":
        med = np.median(a)
        mad = np.median(np.abs(a - med))
        scores = np.zeros(a.size) if mad == 0 else 0.6745 * (a - med) / mad
        return np.abs(scores) > thr, np.clip(scores, -CAP, CAP)
    q1, q3 = np.percentile(a, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - thr * iqr, q3 + thr * iqr
    dist = np.where(a < lo, lo - a, np.where(a > hi, a - hi, 0.0))
    scores = dist / iqr if iqr > 0 else np.where(dist > 0, CAP, 0.0)
    return dist > 0, np.clip(scores, 0, CAP)


def score_point(history, value: float, method: str = "zscore", threshold: Optional[float] = None) -> Tuple[bool, float]:
    """Avalia um ponto novo contra o histórico (sem contaminar as estatísticas com ele)."""
    thr = _thr(method, threshold)
    h = np.asarray(history, dtype=float)
    if h.size < 3:
        return False, 0.0
    if method == "zscore":
        std = h.std(ddof=1)
        if std == 0:
            score = 0.0 if abs(value - h.mean()) < 1e-9 else CAP
        else:
            score = abs(value - h.mean()) / std
        return bool(score > thr), float(min(score, CAP))
    if method == "mad":
        med = np.median(h)
        mad = np.median(np.abs(h - med))
        if mad == 0:
            score = 0.0 if abs(value - med) < 1e-9 else CAP
        else:
            score = abs(0.6745 * (value - med) / mad)
        return bool(score > thr), float(min(score, CAP))
    q1, q3 = np.percentile(h, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - thr * iqr, q3 + thr * iqr
    dist = lo - value if value < lo else (value - hi if value > hi else 0.0)
    score = dist / iqr if iqr > 0 else (CAP if dist > 0 else 0.0)
    return bool(dist > 0), float(min(score, CAP))

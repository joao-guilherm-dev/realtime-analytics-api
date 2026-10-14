import numpy as np
import pytest

from app.analytics import anomaly, engine
from app.analytics.forecast import holt_forecast


def test_describe_basic():
    d = engine.describe([1, 2, 3, 4, 5])
    assert d["count"] == 5 and d["mean"] == 3 and d["median"] == 3 and d["min"] == 1 and d["max"] == 5
    assert engine.describe([]) == {"count": 0}


def test_ewma_converges():
    out = engine.ewma([10] * 20, 0.3)
    assert out[-1] == pytest.approx(10)


def test_linear_trend_up_and_stable():
    ts = np.arange(50, dtype=float)
    up = engine.linear_trend(ts, ts * 2 + 1)
    assert up["direction"] == "alta" and up["slope_per_second"] == pytest.approx(2) and up["r2"] > 0.99
    flat = engine.linear_trend(ts, np.random.default_rng(1).normal(10, 1, 50))
    assert flat["direction"] == "estavel"


def test_aggregate_buckets():
    out = engine.aggregate([0, 1, 2, 10, 11], [1, 2, 3, 10, 20], 10)
    assert len(out) == 2 and out[0]["count"] == 3 and out[0]["mean"] == 2 and out[1]["max"] == 20


def test_correlation_perfect_and_none():
    ts = np.arange(0, 100, 1.0)
    r, n = engine.correlation(ts, ts, ts, ts * 3 + 5, 10)
    assert r == pytest.approx(1.0) and n == 10
    assert engine.correlation(ts, ts, ts, np.ones_like(ts), 10) is None


@pytest.mark.parametrize("method", ["zscore", "iqr", "mad"])
def test_detect_finds_outlier(method):
    rng = np.random.default_rng(0)
    data = np.append(rng.normal(50, 1, 200), 120.0)
    flags, scores = anomaly.detect(data, method)
    assert flags[-1] and flags.sum() <= 10


@pytest.mark.parametrize("method", ["zscore", "iqr", "mad"])
def test_score_point(method):
    hist = list(np.random.default_rng(2).normal(10, 0.5, 100))
    assert anomaly.score_point(hist, 50.0, method)[0] is True
    assert anomaly.score_point(hist, 10.0, method)[0] is False


def test_constant_history_no_inf():
    flag, score = anomaly.score_point([5.0] * 20, 6.0, "zscore")
    assert flag and score == anomaly.CAP


def test_holt_forecast_follows_trend():
    ts = np.arange(30, dtype=float)
    res = holt_forecast(ts, ts * 2.0, steps=5)
    assert res["points"][0]["forecast"] == pytest.approx(60, abs=0.5)
    assert res["points"][-1]["forecast"] > res["points"][0]["forecast"]
    with pytest.raises(ValueError):
        holt_forecast([1, 2], [1, 2])

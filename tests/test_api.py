import numpy as np

from .conftest import make_points


def test_health_is_open(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "realtime-analytics" in r.text


def test_auth_flow(client):
    assert client.post("/api/v1/auth/register", json={"username": "ana_01", "password": "curta"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={"username": "ana_01", "password": "senha12345"}).status_code == 201
    assert client.post("/api/v1/auth/register", json={"username": "ana_01", "password": "senha12345"}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"username": "ana_01", "password": "errada123"}).status_code == 401
    tok = client.post("/api/v1/auth/login", json={"username": "ana_01", "password": "senha12345"}).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.json() == {"username": "ana_01"}


def test_protected_endpoints_need_token(client):
    assert client.get("/api/v1/metrics").status_code == 401
    assert client.get("/api/v1/metrics", headers={"Authorization": "Bearer lixo"}).status_code == 401
    assert client.post("/api/v1/ingest", json={"metric": "x", "value": 1}).status_code == 401


def test_ingest_validation(client, auth):
    assert client.post("/api/v1/ingest", json={"metric": "nome com espaço", "value": 1}, headers=auth).status_code == 422
    assert client.post("/api/v1/ingest", json={"metric": "ok", "value": "abc"}, headers=auth).status_code == 422
    assert client.post("/api/v1/ingest/batch", json={"points": []}, headers=auth).status_code == 422


def test_ingest_stats_series(client, auth, metric):
    vals = list(np.random.default_rng(3).normal(100, 5, 60))
    r = client.post("/api/v1/ingest/batch", json=make_points(metric, vals), headers=auth)
    assert r.status_code == 201 and r.json()["accepted"] == 60

    s = client.get(f"/api/v1/metrics/{metric}/stats", headers=auth).json()
    assert s["stats"]["count"] == 60 and abs(s["stats"]["mean"] - np.mean(vals)) < 1e-6
    assert s["trend"] is not None and s["rate_per_second"] > 0

    ser = client.get(f"/api/v1/metrics/{metric}/series?limit=10", headers=auth).json()
    assert ser["count"] == 10

    names = [m["metric"] for m in client.get("/api/v1/metrics", headers=auth).json()["metrics"]]
    assert metric in names


def test_unknown_metric_404(client, auth):
    assert client.get("/api/v1/metrics/nao_existe/stats", headers=auth).status_code == 404


def test_single_ingest_flags_anomaly(client, auth, metric):
    client.post("/api/v1/ingest/batch", json=make_points(metric, list(np.random.default_rng(4).normal(10, 0.5, 50))), headers=auth)
    r = client.post("/api/v1/ingest", json={"metric": metric, "value": 500}, headers=auth).json()
    assert r["anomaly"] is True and r["score"] > 3


def test_anomalies_endpoint(client, auth, metric):
    vals = list(np.random.default_rng(5).normal(50, 1, 100)) + [200.0]
    client.post("/api/v1/ingest/batch", json=make_points(metric, vals), headers=auth)
    for method in ("zscore", "iqr", "mad"):
        r = client.get(f"/api/v1/metrics/{metric}/anomalies?method={method}", headers=auth).json()
        assert any(a["value"] == 200.0 for a in r["anomalies"]), method


def test_aggregate_and_forecast(client, auth, metric):
    vals = [i * 1.5 for i in range(120)]
    client.post("/api/v1/ingest/batch", json=make_points(metric, vals), headers=auth)
    agg = client.get(f"/api/v1/metrics/{metric}/aggregate?interval=30&seconds=100000000", headers=auth).json()
    assert sum(b["count"] for b in agg["buckets"]) == 120
    fc = client.get(f"/api/v1/metrics/{metric}/forecast?steps=5", headers=auth).json()
    assert len(fc["points"]) == 5 and abs(fc["points"][0]["forecast"] - 120 * 1.5) < 2


def test_correlation(client, auth, metric):
    other = metric + "_b"
    base = list(np.random.default_rng(6).normal(0, 1, 200).cumsum())
    client.post("/api/v1/ingest/batch", json=make_points(metric, base), headers=auth)
    client.post("/api/v1/ingest/batch", json=make_points(other, [v * 2 + 1 for v in base]), headers=auth)
    r = client.get(f"/api/v1/correlation?a={metric}&b={other}&interval=10&seconds=100000000", headers=auth).json()
    assert r["pearson"] > 0.99 and "positiva" in r["interpretation"]


def test_export_csv_and_delete(client, auth, metric):
    client.post("/api/v1/ingest/batch", json=make_points(metric, [1, 2, 3]), headers=auth)
    csv = client.get(f"/api/v1/metrics/{metric}/export.csv", headers=auth)
    assert csv.text.splitlines()[0] == "timestamp,value" and len(csv.text.splitlines()) == 4
    assert client.delete(f"/api/v1/metrics/{metric}", headers=auth).json()["deleted_points"] == 3
    assert client.get(f"/api/v1/metrics/{metric}/stats", headers=auth).status_code == 404


def test_threshold_alert_with_cooldown(client, auth, metric):
    rule = client.post("/api/v1/alerts", json={"metric": metric, "kind": "threshold", "op": "gt",
                                               "threshold": 90, "cooldown_seconds": 60}, headers=auth)
    assert rule.status_code == 201
    rid = rule.json()["id"]
    pts = {"points": [{"metric": metric, "value": 95, "timestamp": 1000.0},
                      {"metric": metric, "value": 96, "timestamp": 1010.0},   # dentro do cooldown
                      {"metric": metric, "value": 97, "timestamp": 1100.0}]}  # depois do cooldown
    assert client.post("/api/v1/ingest/batch", json=pts, headers=auth).json()["alerts_fired"] == 2
    ev = client.get(f"/api/v1/alerts/events?metric={metric}", headers=auth).json()["events"]
    assert len(ev) == 2 and all(e["rule_id"] == rid for e in ev)
    assert client.delete(f"/api/v1/alerts/{rid}", headers=auth).status_code == 200
    assert client.delete(f"/api/v1/alerts/{rid}", headers=auth).status_code == 404


def test_alert_rule_validation(client, auth):
    assert client.post("/api/v1/alerts", json={"metric": "x", "kind": "threshold"}, headers=auth).status_code == 422


def test_anomaly_alert_rule(client, auth, metric):
    rid = client.post("/api/v1/alerts", json={"metric": metric, "kind": "anomaly", "method": "mad"}, headers=auth).json()["id"]
    client.post("/api/v1/ingest/batch", json=make_points(metric, list(np.random.default_rng(7).normal(20, 1, 40))), headers=auth)
    r = client.post("/api/v1/ingest", json={"metric": metric, "value": 300}, headers=auth).json()
    assert r["alerts_fired"] == 1
    client.delete(f"/api/v1/alerts/{rid}", headers=auth)


def test_prometheus(client, auth, metric):
    client.post("/api/v1/ingest", json={"metric": metric, "value": 7}, headers=auth)
    txt = client.get("/prometheus").text
    assert "rtapi_points_ingested_total" in txt and f'metric="{metric}"' in txt


def test_websocket_stream_and_ingest(client, token, auth, metric):
    with client.websocket_connect(f"/ws/metrics/{metric}?token={token}") as sub:
        assert sub.receive_json()["type"] == "snapshot"
        with client.websocket_connect(f"/ws/ingest?token={token}") as ing:
            ing.send_json({"metric": metric, "value": 42.0})
            ack = ing.receive_json()
            assert ack["type"] == "ack" and ack["accepted"] == 1
            ing.send_json({"metric": "inválida!", "value": 1})
            assert ing.receive_json()["type"] == "error"
        ev = sub.receive_json()
        assert ev["type"] == "point" and ev["value"] == 42.0


def test_websocket_rejects_bad_token(client, metric):
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/metrics/{metric}?token=ruim") as ws:
            ws.receive_json()


def test_sse_requires_auth(client, metric):
    assert client.get(f"/api/v1/stream/{metric}").status_code == 401

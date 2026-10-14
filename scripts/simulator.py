"""Gerador de dados fake para ver a API (e o dashboard) funcionando.

Uso:
    python scripts/simulator.py --url http://localhost:8000 --user demo --password demo12345
"""
import argparse
import math
import random
import time

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--user", default="demo")
    ap.add_argument("--password", default="demo12345")
    ap.add_argument("--interval", type=float, default=0.5, help="segundos entre envios")
    ap.add_argument("--spike-chance", type=float, default=0.03)
    args = ap.parse_args()

    c = httpx.Client(base_url=args.url, timeout=10)
    c.post("/api/v1/auth/register", json={"username": args.user, "password": args.password})
    tok = c.post("/api/v1/auth/login", json={"username": args.user, "password": args.password}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"

    # alertas de exemplo
    c.post("/api/v1/alerts", json={"metric": "cpu.usage", "kind": "threshold", "op": "gt", "threshold": 90})
    c.post("/api/v1/alerts", json={"metric": "api.latency_ms", "kind": "anomaly", "method": "mad"})

    print("Enviando dados... Ctrl+C para parar")
    t0 = time.time()
    while True:
        t = time.time() - t0
        spike = random.random() < args.spike_chance
        cpu = 45 + 20 * math.sin(t / 20) + random.gauss(0, 3) + (random.uniform(35, 50) if spike else 0)
        mem = 60 + t * 0.02 + random.gauss(0, 1.5)
        lat = 120 + 0.8 * (cpu - 45) + random.gauss(0, 8) + (random.uniform(200, 400) if spike else 0)
        batch = {"points": [
            {"metric": "cpu.usage", "value": round(min(cpu, 100), 2), "tags": {"host": "srv-01"}},
            {"metric": "mem.usage", "value": round(min(mem, 100), 2), "tags": {"host": "srv-01"}},
            {"metric": "api.latency_ms", "value": round(max(lat, 1), 2), "tags": {"route": "/login"}},
        ]}
        r = c.post("/api/v1/ingest/batch", json=batch)
        info = r.json()
        print(f"t={t:6.1f}s cpu={batch['points'][0]['value']:6.2f} anomalias={info.get('anomalies')} alertas={info.get('alerts_fired')}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

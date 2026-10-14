"""Motor de regras de alerta (limiar e anomalia) com cooldown."""
import operator
from typing import Dict, List, Tuple

from .analytics.anomaly import score_point

OPS = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le, "eq": operator.eq}
SYMBOLS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=="}
MIN_HISTORY = 10


class AlertEngine:
    def __init__(self) -> None:
        self.rules: List[Dict] = []
        self._last_fired: Dict[Tuple[int, str], float] = {}

    def load(self, rules: List[Dict]) -> None:
        self.rules = list(rules)

    def add(self, rule: Dict) -> None:
        self.rules.append(rule)

    def remove(self, rule_id: int) -> None:
        self.rules = [r for r in self.rules if r["id"] != rule_id]
        self._last_fired = {k: v for k, v in self._last_fired.items() if k[0] != rule_id}

    def evaluate(self, metric: str, value: float, ts: float, history: List[float]) -> List[Dict]:
        fired: List[Dict] = []
        for r in self.rules:
            if not r.get("active", 1) or r["metric"] not in (metric, "*"):
                continue
            if r["kind"] == "threshold":
                if not OPS[r["op"]](value, r["threshold"]):
                    continue
                msg = f"{metric}={value:g} {SYMBOLS[r['op']]} {r['threshold']:g}"
            else:
                if len(history) < MIN_HISTORY:
                    continue
                is_anom, score = score_point(history, value, r["method"], r.get("sensitivity"))
                if not is_anom:
                    continue
                msg = f"anomalia em {metric}={value:g} ({r['method']}, score={score:.2f})"
            key = (r["id"], metric)
            last = self._last_fired.get(key)
            if last is not None and 0 <= ts - last < r["cooldown_seconds"]:
                continue
            self._last_fired[key] = ts
            fired.append({"rule_id": r["id"], "metric": metric, "ts": ts, "value": value, "message": msg})
        return fired

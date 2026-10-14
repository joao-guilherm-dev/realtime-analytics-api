import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

METRIC_PATTERN = r"^[A-Za-z0-9_.\-]{1,64}$"


class RegisterIn(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.\-]{3,32}$")
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class IngestPoint(BaseModel):
    metric: str = Field(pattern=METRIC_PATTERN, examples=["cpu.usage"])
    value: float = Field(allow_inf_nan=False, examples=[42.5])
    timestamp: Optional[float] = Field(default=None, description="Unix epoch em segundos (opcional)")
    tags: Dict[str, str] = Field(default_factory=dict, max_length=16)


class IngestBatch(BaseModel):
    points: List[IngestPoint] = Field(min_length=1, max_length=1000)


class AlertRuleCreate(BaseModel):
    metric: str = Field(description="Nome da métrica ou '*' para todas")
    kind: Literal["threshold", "anomaly"] = "threshold"
    op: Optional[Literal["gt", "gte", "lt", "lte", "eq"]] = None
    threshold: Optional[float] = Field(default=None, allow_inf_nan=False)
    method: Literal["zscore", "iqr", "mad"] = "zscore"
    sensitivity: Optional[float] = Field(default=None, gt=0)
    cooldown_seconds: int = Field(default=60, ge=0, le=86400)

    @model_validator(mode="after")
    def _check(self):
        if self.metric != "*" and not re.match(METRIC_PATTERN, self.metric):
            raise ValueError("metric inválida")
        if self.kind == "threshold" and (self.op is None or self.threshold is None):
            raise ValueError("regras 'threshold' exigem 'op' e 'threshold'")
        return self

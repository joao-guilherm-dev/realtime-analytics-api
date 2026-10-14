from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..schemas import AlertRuleCreate
from ..security import current_user
from ..state import state

router = APIRouter(prefix="/alerts", tags=["Alertas"])


@router.post("", status_code=201, summary="Cria regra (limiar ou anomalia)")
def create_rule(rule: AlertRuleCreate, user: str = Depends(current_user)):
    created = state.db.add_rule(rule.model_dump(), created_by=user)
    state.alerts.add(created)
    return created


@router.get("", summary="Lista regras")
def list_rules(_: str = Depends(current_user)):
    return {"rules": state.alerts.rules}


@router.delete("/{rule_id}", summary="Remove regra")
def delete_rule(rule_id: int, _: str = Depends(current_user)):
    if not state.db.delete_rule(rule_id):
        raise HTTPException(404, "Regra não encontrada")
    state.alerts.remove(rule_id)
    return {"deleted": rule_id}


@router.get("/events", summary="Histórico de alertas disparados")
def events(limit: int = Query(50, ge=1, le=1000), metric: Optional[str] = None, _: str = Depends(current_user)):
    return {"events": state.db.list_events(limit, metric)}

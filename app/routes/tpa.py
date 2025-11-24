from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session
from app.db.session import get_session
from app.services.tpa_ingestion import TPAIngestionService
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

# --- Pydantic Models for Ingestion ---

class EligibilityItem(BaseModel):
    member_id: str
    first_name: str
    last_name: str
    date_of_birth: str # YYYY-MM-DD
    phone_number: str
    plan_id: Optional[int] = None
    risk_tier: Optional[str] = "Low"

class AccumulatorItem(BaseModel):
    member_id: str
    deductible_met: float
    oop_met: float
    deductible_limit: Optional[float] = 3000.0
    oop_limit: Optional[float] = 6000.0

class ClaimItem(BaseModel):
    member_id: str
    date_of_service: str # YYYY-MM-DD
    cpt_code: str
    diagnosis_code: Optional[str] = None
    allowed_amount: float
    provider_npi: Optional[str] = None

class ReferralItem(BaseModel):
    member_id: str
    cpt_code: str
    provider_npi: Optional[str] = None

# --- Endpoints ---

@router.post("/ingest/eligibility")
async def ingest_eligibility(
    payload: List[EligibilityItem], 
    session: Session = Depends(get_session)
):
    service = TPAIngestionService(session)
    data = [item.dict() for item in payload]
    return service.ingest_eligibility(data)

@router.post("/ingest/accumulators")
async def ingest_accumulators(
    payload: List[AccumulatorItem],
    session: Session = Depends(get_session)
):
    service = TPAIngestionService(session)
    data = [item.dict() for item in payload]
    return service.ingest_accumulators(data)

@router.post("/ingest/claims")
async def ingest_claims(
    payload: List[ClaimItem],
    session: Session = Depends(get_session)
):
    service = TPAIngestionService(session)
    data = [item.dict() for item in payload]
    return service.ingest_claims(data)

@router.post("/ingest/referrals")
async def ingest_referrals(
    payload: List[ReferralItem],
    session: Session = Depends(get_session)
):
    service = TPAIngestionService(session)
    data = [item.dict() for item in payload]
    return service.ingest_referrals(data)


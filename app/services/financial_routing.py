from sqlmodel import Session, select
from app.db.models import Eligibility, Plan, Accumulator, EOB
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class FinancialRoutingService:
    def __init__(self, session: Session):
        self.session = session

    def should_engage(self, member_id: int, cpt_code: str, estimated_cost: float) -> dict:
        """
        Determines if we should engage the member based on financial logic.
        Returns a dict with decision (bool) and reason (str).
        """
        member = self.session.get(Eligibility, member_id)
        if not member:
            return {"engage": False, "reason": "Member not found"}

        # 1. Get Accumulators (Latest)
        accumulator = self.session.exec(
            select(Accumulator)
            .where(Accumulator.member_id == member_id)
            .order_by(Accumulator.timestamp.desc())
        ).first()
        
        # Default if no accumulator found
        deductible_met = accumulator.deductible_met if accumulator else 0.0
        deductible_limit = accumulator.deductible_limit if accumulator else 3000.0
        deductible_remaining = max(0, deductible_limit - deductible_met)
        
        # 2. Check Risk Tier
        # If High Risk, we engage regardless of immediate savings to steer behavior
        if member.risk_tier == "High":
            return {"engage": True, "reason": "High Risk Member - Always Engage"}
            
        # 3. Financial Calculation
        # Simple Logic: 
        # If they haven't met deductible, they pay everything up to the limit.
        # If estimated_cost < deductible_remaining, Member pays 100%. Employer pays $0.
        # In this case, Employer saves nothing by redirecting, UNLESS we want to help the member (Goodwill).
        # The prompt says: "Redirect below-deductible members only when net savings is positive or when the member is medium/high risk."
        
        # "Net savings positive" implies Employer pays something.
        # Employer pays = max(0, Cost - Deductible_Remaining) * (1 - Coinsurance_Rate)
        # Let's assume 20% coinsurance (Plan pays 80%) after deductible.
        
        # Scenario A: Hospital (High Cost)
        # Hospital_Cost = $2000
        # Deductible_Remaining = $3000
        # Member Pays $2000. Employer Pays $0.
        # Savings = 0.
        
        # Scenario B: Freestanding (Low Cost)
        # Freestanding_Cost = $500
        # Member Pays $500. Employer Pays $0.
        # Savings = 0.
        
        # Conclusion: If fully below deductible, Employer savings is 0.
        # So we only engage if Risk is Medium/High OR if they are exceeding deductible.
        
        if member.risk_tier == "Medium":
             return {"engage": True, "reason": "Medium Risk Member - Engage for Behavior"}
             
        # Low Risk Logic
        if estimated_cost > deductible_remaining:
            # They will hit deductible and Employer will start paying.
            # We assume we can find a cheaper option (Freestanding).
            # If we assume Hospital is 3x Freestanding (generic rule of thumb or use data if available).
            # Let's assume the incoming 'estimated_cost' IS the Hospital price (since it's a referral).
            
            # If we don't have a specific hospital price, we can't calculate exact savings.
            # But if they are exceeding deductible, there is POTENTIAL savings.
            return {"engage": True, "reason": "Exceeds Deductible - Potential Savings"}
            
        else:
            # Below deductible, Low Risk.
            # Employer pays nothing either way.
            return {"engage": False, "reason": "Below Deductible & Low Risk - No Employer Savings"}

    def calculate_savings(self, plan_id: int, cpt_code: str) -> float:
        """
        Estimates potential savings based on average spread in EOB data.
        """
        # Get average cost for this CPT in this Plan
        eobs = self.session.exec(select(EOB).where(EOB.plan_id == plan_id, EOB.cpt_code == cpt_code)).all()
        if not eobs:
            return 0.0
            
        amounts = [e.allowed_amount for e in eobs]
        avg_cost = sum(amounts) / len(amounts)
        min_cost = min(amounts)
        
        # Potential savings is Avg - Min (rough estimate)
        return avg_cost - min_cost

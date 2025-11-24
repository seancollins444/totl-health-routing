from sqlmodel import Session, select
from app.db.models import Eligibility, Accumulator, ReferralEvent, Facility, MemberInteraction
from datetime import datetime

class RoutingEngine:
    def __init__(self, session: Session):
        self.session = session
        # Common Routine Labs CPTs (Demo Requirement)
        self.ROUTINE_LABS = ["80050", "80053", "85025", "80061", "80048"]

    def evaluate_referral(self, referral: ReferralEvent) -> dict:
        """
        Evaluate a referral event to determine if we should engage the member.
        Returns dict with 'engage' (bool) and 'reason' (str).
        """
        member = referral.member
        cpt_code = referral.cpt_code
        
        # 1. Get Accumulators
        accumulator = self.session.exec(select(Accumulator).where(Accumulator.member_id == member.id)).first()
        if not accumulator:
            # Default to 0 met if no record
            deductible_remaining = 3000.0 
        else:
            deductible_remaining = max(0, accumulator.deductible_limit - accumulator.deductible_met)

        # 2. Calculate Savings (Mocked for MVP)
        # In real world, we'd look up rates for the referred provider vs our network
        # For demo: 
        # Hospital (High Cost) ~ $500 for labs
        # Freestanding (Low Cost) ~ $50 for labs
        hospital_rate = 500.0
        freestanding_rate = 50.0
        potential_savings = hospital_rate - freestanding_rate

        # 3. Risk Tier
        risk_tier = member.risk_tier # Low, Medium, High

        # 4. Logic
        # Engage if:
        # - Savings exist (> $0)
        # - AND (Deductible is NOT met OR Risk is Medium/High)
        # Note: If deductible is met, member pays 0 (or coinsurance), so they care less about cost.
        # But employer still cares. 
        # User Req: "Redirect below-deductible members only when net savings is positive or when the member is medium/high risk."
        
        engage = False
        reason = ""

        if potential_savings <= 0:
            engage = False
            reason = "No savings opportunity"
        else:
            if deductible_remaining > 0:
                # Member is paying out of pocket (mostly), so they are incentivized to save.
                engage = True
                reason = f"Deductible remaining (${deductible_remaining}). Savings available."
            else:
                # Deductible met. Member pays little/nothing.
                if risk_tier in ["Medium", "High"]:
                    engage = True
                    reason = f"Deductible met, but High Risk Member ({risk_tier}). Engagement valuable for care management."
                else:
                    engage = False
                    reason = "Deductible met and Low Risk. Member unlikely to switch."

        # Demo Override for Routine Labs
        if cpt_code in self.ROUTINE_LABS:
             # Ensure we engage for the demo flow if it's a routine lab, unless explicitly suppressed?
             # Actually, the logic above should handle it. 
             # If Sean is High Risk (set in seed), he should be engaged even if deductible met.
             # If Sean has Low Deductible Met (set in seed), he should be engaged.
             pass

        return {"engage": engage, "reason": reason}
    
    def calculate_financial_viability(self, member, cpt_code: str, matches: list) -> dict:
        """
        Determine if member can achieve $0 out-of-pocket cost.
        
        Returns:
        {
            "viable_for_zero": bool,
            "estimated_oop": float,
            "reasoning": str
        }
        """
        from app.db.models import Accumulator
        
        # Get accumulator
        accumulator = self.session.exec(select(Accumulator).where(Accumulator.member_id == member.id)).first()
        
        if not accumulator:
            return {
                "viable_for_zero": False,
                "estimated_oop": 0,
                "reasoning": "No accumulator data available"
            }
        
        # Check if deductible is met
        deductible_remaining = max(0, accumulator.deductible_limit - accumulator.deductible_met)
        oop_remaining = max(0, accumulator.oop_limit - accumulator.oop_met)
        
        # If deductible is met, members typically pay coinsurance (e.g., 20%)
        # If a facility offers a lower price that results in $0 after insurance, member pays $0
        # For MVP: viable_for_zero = deductible met AND we have a low-cost option
        
        if deductible_remaining == 0:
            # Deductible met - check if cheapest option is low enough for $0 OOP
            if matches and len(matches) > 0:
                cheapest_price = matches[0].get('price', 999999)
                
                # Simplified logic: if price is very low (< $100), likely $0 after insurance
                # In production, this would use actual coinsurance rates
                if cheapest_price < 100:
                    return {
                        "viable_for_zero": True,
                        "estimated_oop": 0,
                        "reasoning": "Deductible met, low-cost facility available"
                    }
                else:
                    # Member might pay coinsurance (e.g., 20%)
                    estimated_coinsurance = cheapest_price * 0.2
                    return {
                        "viable_for_zero": False,
                        "estimated_oop": estimated_coinsurance,
                        "reasoning": f"Deductible met but coinsurance applies (~${int(estimated_coinsurance)})"
                    }
            else:
                return {
                    "viable_for_zero": False,
                    "estimated_oop": 0,
                    "reasoning": "No pricing data available"
                }
        else:
            # Deductible not met - member pays full cost until deductible is reached
            # Not viable for $0 unless it's a preventive service (not implemented yet)
            if matches and len(matches) > 0:
                cheapest_price = matches[0].get('price', 0)
                estimated_oop = min(cheapest_price, deductible_remaining)
                
                return {
                    "viable_for_zero": False,
                    "estimated_oop": estimated_oop,
                    "reasoning": f"Deductible not met (${int(deductible_remaining)} remaining)"
                }
            else:
                return {
                    "viable_for_zero": False,
                    "estimated_oop": deductible_remaining,
                    "reasoning": "Deductible not met, no pricing data"
                }

from sqlmodel import Session, select, func
from app.db.models import EOB, CPTApprovalRule, Facility
from typing import List, Dict, Optional

class PricingService:
    def __init__(self, session: Session):
        self.session = session

    def find_cheapest_facilities(self, plan_id: int, cpt_codes: List[str], member_zip: str = None) -> List[Dict]:
        """
        Finds the cheapest facilities for the given CPT codes under the plan.
        Returns a list of facilities with pricing info.
        """
        if not cpt_codes:
            return []

        # For MVP, we'll focus on the primary CPT (first one) or iterate.
        # Let's aggregate results.
        
        # 1. Get approved NPIs for this plan and CPTs
        # We need to find NPIs that are approved for AT LEAST ONE of the CPTs?
        # Or usually, we route based on the main procedure.
        # Let's assume the first CPT is the primary one for routing.
        primary_cpt = cpt_codes[0]
        
        # 2. Query EOBs for this plan and CPT
        # We want the lowest allowed_amount per NPI
        statement = (
            select(EOB.npi, func.min(EOB.allowed_amount).label("min_price"))
            .where(EOB.plan_id == plan_id)
            .where(EOB.cpt_code == primary_cpt)
            .group_by(EOB.npi)
            .order_by(func.min(EOB.allowed_amount))
        )
        
        results = self.session.exec(statement).all()
        
        if not results:
            return []
            
        # 3. Logic: Cheapest + within 10%
        cheapest_price = results[0][1]
        threshold = cheapest_price * 1.10
        
        eligible_npis = []
        for npi, price in results:
            if price <= threshold:
                eligible_npis.append({"npi": npi, "price": price})
        
        # 4. Enrich with Facility details and apply geo-filtering
        from app.services.geo_service import calculate_distance
        
        final_results = []
        for item in eligible_npis[:10]: # Get more candidates for geo-filtering
            facility = self.session.exec(
                select(Facility).where(Facility.npi == item["npi"])
            ).first()
            
            if facility:
                # Calculate distance if member zip is provided
                distance = 0.0
                if member_zip and facility.zip_code:
                    distance = calculate_distance(member_zip, facility.zip_code)
                
                # Calculate potential savings (compared to most expensive option)
                if results:
                    max_price = results[-1][1] if len(results) > 1 else item["price"] * 2
                    savings = max_price - item["price"]
                else:
                    savings = 0
                
                # Determine max acceptable distance based on savings
                # Default: 10 miles
                # High savings (>$1000): up to 25 miles
                # Medium savings ($500-$1000): up to 15 miles
                if savings > 1000:
                    max_distance = 25
                elif savings > 500:
                    max_distance = 15
                else:
                    max_distance = 10
                
                # Apply distance filter
                if member_zip and facility.zip_code:
                    if distance > max_distance:
                        continue  # Skip this facility, too far
                
                final_results.append({
                    "name": facility.facility_name,
                    "address": f"{facility.address}, {facility.city}, {facility.state}",
                    "price": item["price"],
                    "distance": distance,
                    "zip_code": facility.zip_code
                })
            else:
                # Fallback if facility details missing but we have NPI/Price from EOB
                eob_name = self.session.exec(
                    select(EOB.facility_name)
                    .where(EOB.npi == item["npi"])
                    .limit(1)
                ).first()
                final_results.append({
                    "name": eob_name or "Unknown Facility",
                    "address": "Address not on file",
                    "price": item["price"],
                    "distance": 999,  # Unknown
                    "zip_code": None
                })
            
            # Limit to top 3 after filtering
            if len(final_results) >= 3:
                break
                
        return final_results

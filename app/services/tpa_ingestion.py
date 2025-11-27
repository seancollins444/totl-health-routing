from sqlmodel import Session, select
from app.db.models import Eligibility, Accumulator, Claim, ReferralEvent, Plan, Employer, MemberInteraction
from datetime import datetime, date
from app.core.utils import normalize_phone_number

class TPAIngestionService:
    def __init__(self, session: Session):
        self.session = session

    def ingest_eligibility(self, data: list[dict]):
        """
        Ingest eligibility data (834-like).
        Expected format: list of dicts with member details.
        """
        results = {"processed": 0, "errors": []}
        for row in data:
            try:
                # Find or create member
                member = self.session.exec(select(Eligibility).where(Eligibility.member_id == row["member_id"])).first()
                if not member:
                    # Assume plan_id is provided or lookup by plan_name/group_id
                    # For MVP, assuming plan_id is passed or we default to a known plan
                    plan_id = row.get("plan_id")
                    if not plan_id:
                        # Fallback to first plan for demo simplicity if not provided
                        plan = self.session.exec(select(Plan)).first()
                        plan_id = plan.id if plan else None
                    
                    member = Eligibility(
                        member_id=row["member_id"],
                        first_name=row["first_name"],
                        last_name=row["last_name"],
                        date_of_birth=datetime.strptime(row["date_of_birth"], "%Y-%m-%d").date(),
                        phone_number=normalize_phone_number(row["phone_number"]),
                        plan_id=plan_id,
                        risk_tier=row.get("risk_tier", "Low")
                    )
                    self.session.add(member)
                else:
                    # Update fields
                    member.first_name = row.get("first_name", member.first_name)
                    member.last_name = row.get("last_name", member.last_name)
                    member.phone_number = row.get("phone_number", member.phone_number)
                    if "risk_tier" in row:
                        member.risk_tier = row["risk_tier"]
                    self.session.add(member)
                
                results["processed"] += 1
            except Exception as e:
                results["errors"].append(f"Error processing {row.get('member_id')}: {str(e)}")
        
        self.session.commit()
        return results

    def ingest_accumulators(self, data: list[dict]):
        """
        Ingest accumulator snapshots.
        Expected format: list of dicts with member_id and values.
        """
        results = {"processed": 0, "errors": []}
        for row in data:
            try:
                member = self.session.exec(select(Eligibility).where(Eligibility.member_id == row["member_id"])).first()
                if not member:
                    results["errors"].append(f"Member not found: {row.get('member_id')}")
                    continue

                acc = self.session.exec(select(Accumulator).where(Accumulator.member_id == member.id)).first()
                if not acc:
                    acc = Accumulator(member_id=member.id)
                
                acc.deductible_met = float(row.get("deductible_met", 0.0))
                acc.oop_met = float(row.get("oop_met", 0.0))
                acc.deductible_limit = float(row.get("deductible_limit", 3000.0))
                acc.oop_limit = float(row.get("oop_limit", 6000.0))
                acc.timestamp = datetime.utcnow()
                
                self.session.add(acc)
                results["processed"] += 1
            except Exception as e:
                results["errors"].append(f"Error processing acc for {row.get('member_id')}: {str(e)}")
        
        self.session.commit()
        return results

    def ingest_claims(self, data: list[dict]):
        """
        Ingest historical claims.
        """
        results = {"processed": 0, "errors": []}
        for row in data:
            try:
                member = self.session.exec(select(Eligibility).where(Eligibility.member_id == row["member_id"])).first()
                if not member:
                    results["errors"].append(f"Member not found: {row.get('member_id')}")
                    continue

                claim = Claim(
                    member_id=member.id,
                    date_of_service=datetime.strptime(row["date_of_service"], "%Y-%m-%d").date(),
                    cpt_code=row["cpt_code"],
                    diagnosis_code=row.get("diagnosis_code"),
                    allowed_amount=float(row["allowed_amount"]),
                    provider_npi=row.get("provider_npi")
                )
                self.session.add(claim)
                results["processed"] += 1
            except Exception as e:
                results["errors"].append(f"Error processing claim for {row.get('member_id')}: {str(e)}")
        
        self.session.commit()
        return results

    def ingest_referrals(self, data: list[dict]):
        """
        Ingest referral/ordering events.
        Triggers routing logic immediately.
        """
        results = {"processed": 0, "errors": []}
        # Import here to avoid circular dependency if routing engine imports this
        from app.services.routing_engine import RoutingEngine 
        
        routing_engine = RoutingEngine(self.session)

        for row in data:
            try:
                member = self.session.exec(select(Eligibility).where(Eligibility.member_id == row["member_id"])).first()
                if not member:
                    results["errors"].append(f"Member not found: {row.get('member_id')}")
                    continue

                # Calculate Baseline (What would have happened)
                baseline_npi = row.get("provider_npi")
                baseline_allowed = 0.0
                
                if baseline_npi:
                    # Look up price for this NPI and CPT
                    from app.db.models import EOB
                    eob = self.session.exec(
                        select(EOB)
                        .where(EOB.npi == baseline_npi)
                        .where(EOB.cpt_code == row["cpt_code"])
                        .where(EOB.plan_id == member.plan_id)
                    ).first()
                    if eob:
                        baseline_allowed = eob.allowed_amount

                # Create Referral Event
                referral = ReferralEvent(
                    member_id=member.id,
                    cpt_code=row["cpt_code"],
                    ordering_provider_npi=row.get("ordering_provider_npi"), # If provided
                    baseline_npi=baseline_npi,
                    baseline_allowed=baseline_allowed,
                    plan_cost_baseline=baseline_allowed, # Assuming 0 member share for now or calc later
                    timestamp=datetime.utcnow(),
                    status="received"
                )
                self.session.add(referral)
                self.session.commit() # Commit to get ID
                self.session.refresh(referral)

                # Trigger Routing Logic
                routing_result = routing_engine.evaluate_referral(referral)
                
                # Calculate financial viability (Real Check)
                from app.services.pricing_service import PricingService
                pricing = PricingService(self.session)
                matches = pricing.find_cheapest_facilities(member.plan_id, [row["cpt_code"]], member_zip=member.zip_code)
                
                accumulator = self.session.exec(select(Accumulator).where(Accumulator.member_id == member.id)).first()
                # Calculate deductible remaining
                deductible_remaining = 3000.0 # Default
                if accumulator:
                    deductible_remaining = max(0, accumulator.deductible_limit - accumulator.deductible_met)
                
                # Check viability
                viability = routing_engine.calculate_financial_viability(member, row["cpt_code"], matches)
                viable_for_zero = viability["viable_for_zero"]
                
                # Proactive Rules Logic

                # Determine if we should engage based on NEW Decision Tree
                # We engage if:
                # 1. Viable for $0 (Paths 1.1, 1.3)
                # 2. OR Routing Engine says so (Risk based, etc - though User Rules imply strict viability for proactive)
                
                # User Rules: "Proactive messages only go out when BOTH: member has opted in (or needs opt-in AND viable) AND the episode is financially viable for $0"
                # So actually, if NOT viable_for_zero, we NEVER send proactive SMS.
                # So `engage` is effectively `viable_for_zero`.
                
                # Relaxed Rule: Engage if viable for $0 OR if Routing Engine suggests it (e.g. savings available)
                print(f"DEBUG TPA: viable_for_zero={viable_for_zero}, routing_engage={routing_result['engage']}, reason={routing_result['reason']}", flush=True)
                should_engage = viable_for_zero or routing_result['engage']
                
                if should_engage:
                    referral.status = "engaged"
                    
                    # SMS Decision Tree Implementation
                    from app.services.twilio_service import TwilioService
                    from app.services.cpt_service import CPTService
                    from app.services.referral_image_service import ReferralImageService
                    
                    cpt_service = CPTService()
                    image_service = ReferralImageService()
                    
                    # Get member's plan name
                    plan_name = member.plan.name if member.plan else "your health plan"
                    member_name = member.first_name
                    
                    # Get friendly service name
                    service_name = cpt_service.get_description(row["cpt_code"])
                    
                    # Generate custom referral image
                    # We need provider name, let's assume "Dr. Smith" or lookup if we had provider table
                    provider_name = "Dr. John Smith" 
                    media_url = image_service.generate_generic_referral(
                        member_name=f"{member.first_name} {member.last_name}",
                        provider_name=provider_name,
                        test_name=service_name
                    )
                    
                    # Full URL for Twilio (needs to be reachable, but for demo localhost is fine if we just want to log it)
                    # Ideally we'd use ngrok, but for local demo console display, relative path or localhost is fine.
                    # Twilio won't actually fetch it if it's localhost, but our demo console will display it.
                    full_media_url = f"http://localhost:8000{media_url}"
                    
                    # DECISION TREE: TPA Referral (Proactive)
                    # Rules:
                    # 1.1 Not opted-in + financially viable ($0) -> Send Opt-in
                    # 1.2 Not opted-in + NOT financially viable -> Send NOTHING (Handled by should_engage=False)
                    # 1.3 Opted-in + financially viable ($0) -> Send Direction
                    # 1.4 Opted-in + NOT financially viable -> Send NOTHING (Handled by should_engage=False)
                    
                    msg = None
                    
                    if member.opted_in:
                        # Path 1.3: Opted-in + Viable ($0)
                        if matches:
                            site_name = matches[0]['name']
                            msg = (
                                f"Hi {member_name}, your doctor ordered {service_name}. "
                                f"You can get this with no out of pocket cost at {site_name}."
                            )
                        else:
                            # Should not happen if viable_for_zero is true, but fallback
                            msg = None
                            
                    else:
                        # Path 1.1: Not Opted-in + Viable ($0)
                        msg = (
                            f"Hi {member_name}, {plan_name} works with Totl to help you get certain tests "
                            f"with no out of pocket cost. You have a new referral. "
                            f"Reply YES to see your $0 options."
                        )
                    
                    # Send SMS and log if message was generated
                    if msg:
                        # Normalize phone number for check
                        from app.core.utils import normalize_phone_number
                        normalized_phone = normalize_phone_number(member.phone_number)
                        
                        # Explicitly check OptOut here to be safe
                        from app.db.models import OptOut
                        opt_out_check = self.session.exec(select(OptOut).where(OptOut.phone_number == normalized_phone)).first()
                        
                        if opt_out_check:
                            # Log blocked SMS
                            # print(f"BLOCKED proactive SMS to {normalized_phone} due to OptOut record.", flush=True)
                            sid = None
                        else:
                            twilio = TwilioService()
                            sid = twilio.send_sms(member.phone_number, msg, media_url=full_media_url, session=self.session)
                        
                        # Log Interaction only if sent
                        if sid:
                            self.session.add(MemberInteraction(
                                member_id=member.id,
                                message_type="outbound_referral_trigger",
                                content=msg + f" [Image: {full_media_url}]"
                            ))
                    else:
                        # Should not happen given should_engage logic, but safe fallback
                        pass
                else:
                    referral.status = "suppressed"
                    # Log Interaction (Suppressed)
                    self.session.add(MemberInteraction(
                        member_id=member.id,
                        message_type="suppressed",
                        content=f"Referral {row['cpt_code']} suppressed (Non-Viable) - No SMS Sent"
                    ))
                
                self.session.add(referral)
                
                results["processed"] += 1
            except Exception as e:
                results["errors"].append(f"Error processing referral for {row.get('member_id')}: {str(e)}")
        
        self.session.commit()
        return results


import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine
from app.db.models import Eligibility, Plan, ReferralEvent, Accumulator
from app.services.tpa_ingestion import TPAIngestionService
from app.services.twilio_service import TwilioService
from datetime import date, datetime

# Setup in-memory DB
engine = create_engine("sqlite:///:memory:")

@pytest.fixture(name="session")
def session_fixture():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

@patch("app.services.twilio_service.TwilioService.send_sms")
def test_tpa_ingestion_respects_stop(mock_send_sms, session):
    # 1. Setup Data
    # Create Plan
    plan = Plan(id=1, name="Test Plan", employer_id=1)
    session.add(plan)
    
    # Create Member who is OPTED OUT
    member = Eligibility(
        member_id="MEM_STOP",
        first_name="Stop",
        last_name="User",
        phone_number="+15559998888",
        date_of_birth=date(1990, 1, 1),
        plan_id=1,
        opted_out=True, # <--- KEY
        opted_in=False
    )
    session.add(member)
    session.commit()
    
    # 2. Ingest Referral (Viable for $0 to trigger proactive SMS)
    # We need to mock PricingService to return a cheap option
    with patch("app.services.pricing_service.PricingService.find_cheapest_facilities") as mock_pricing:
        # Use "Freestanding" in name to trigger logic in routing_engine
        mock_pricing.return_value = [{"name": "Cheap Lab Freestanding", "price": 4.0}]
        
        # We also need to ensure RoutingEngine sees it as viable
        # RoutingEngine uses DB accumulator. Let's add one with deductible met or ensure logic passes.
        # If no accumulator, defaults to 3000 remaining.
        # But if price is < deductible, OOP is price.
        # Wait, the logic for "viable_for_zero" in routing_engine.py:
        # if deductible_remaining == 0: ...
        # OR if deductible not met ...
        
        # Let's force deductible met
        acc = Accumulator(
            member_id=member.id, 
            deductible_limit=3000.0, 
            deductible_met=3000.0, # Met
            oop_limit=6000.0, 
            oop_met=0.0,
            timestamp=datetime.utcnow()
        )
        session.add(acc)
        session.commit()
        
        # 3. Run Ingestion
        service = TPAIngestionService(session)
        data = [{
            "member_id": "MEM_STOP",
            "cpt_code": "80050", # Routine lab
            "provider_npi": "1234567890"
        }]
        
        # We need to mock image generation too to avoid errors
        with patch("app.services.referral_image_service.ReferralImageService.generate_generic_referral") as mock_img:
            mock_img.return_value = "/static/test.png"
            
            service.ingest_referrals(data)
            
    # 4. Assertions
    # The bug is that send_sms IS called because session wasn't passed to it,
    # and TwilioService only checks DB if session is provided.
    # So we expect mock_send_sms.call_count to be 1 (reproducing the bug).
    # After fix, it should be 0 OR called with session and return None (if we mock the return).
    
    # For verification, we assert it WAS called (logic still tries to send)
    assert mock_send_sms.called, "SMS logic should still attempt to send (but be blocked by service)"
    
    # Verify arguments - session SHOULD be passed now
    call_args = mock_send_sms.call_args
    
    # Check if session was passed in kwargs
    assert "session" in call_args.kwargs and call_args.kwargs["session"] is not None, "Fix failed: Session was NOT passed to send_sms"


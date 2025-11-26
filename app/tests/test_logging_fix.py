
import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine, select
from app.db.models import Eligibility, OptOut, Plan, Employer, MemberInteraction, Accumulator
from app.services.twilio_service import TwilioService
from app.services.tpa_ingestion import TPAIngestionService
from datetime import date
from app.core.utils import normalize_phone_number

# Setup in-memory DB
engine = create_engine("sqlite:///:memory:")

@pytest.fixture(name="session")
def session_fixture():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

def test_blocked_sms_is_not_logged(session):
    # 1. Setup Data
    employer = Employer(name="TechStart", notes="Test")
    session.add(employer)
    session.commit()
    
    plan = Plan(name="TechStart HDHP", employer_id=employer.id)
    session.add(plan)
    session.commit()
    
    jane = Eligibility(
        member_id="MEM001",
        first_name="Jane",
        last_name="Doe",
        phone_number="5551234567",
        date_of_birth=date(1990, 1, 1),
        zip_code="12345",
        plan_id=plan.id,
        opted_in=False
    )
    session.add(jane)
    session.commit()
    
    # Add Accumulator
    session.add(Accumulator(
        member_id=jane.id,
        deductible_met=3000.0, # Met
        oop_met=1000.0,
        deductible_limit=3000.0,
        oop_limit=6000.0
    ))
    session.commit()
    
    # 2. Opt Out Jane
    normalized_number = normalize_phone_number(jane.phone_number)
    session.add(OptOut(phone_number=normalized_number, reason="Test"))
    session.commit()
    
    # 3. Trigger Referral
    service = TPAIngestionService(session)
    
    # Mock PricingService to ensure viability
    with patch('app.services.pricing_service.PricingService.find_cheapest_facilities') as mock_pricing:
        mock_pricing.return_value = [{"name": "Cheap Lab", "price": 0.0, "distance": 5.0}]
        
        # Mock Twilio Client
        with patch('app.services.twilio_service.Client') as MockClient:
            # We don't even need to mock create, because send_sms should return None early
    
            service.ingest_referrals([{
                "member_id": "MEM001",
                "cpt_code": "73721",
                "provider_npi": "1111111111"
            }])
        
        # 4. Verify MemberInteraction is NOT created
        interactions = session.exec(select(MemberInteraction).where(MemberInteraction.member_id == jane.id)).all()
        assert len(interactions) == 0, "Interaction WAS logged despite SMS being blocked!"


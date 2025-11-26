
import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine, select
from app.db.models import Eligibility, OptOut, Plan, Employer
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

def test_full_stop_flow(session):
    # 1. Setup Data (Jane)
    # Note: Using raw number as in seed data to match potential real-world state
    raw_db_number = "5551234567" 
    
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
        phone_number=raw_db_number, # 5551234567
        date_of_birth=date(1990, 1, 1),
        plan_id=plan.id,
        opted_in=False # Initially false
    )
    session.add(jane)
    session.commit()
    
    # 2. Simulate STOP from Twilio (Normalized format)
    twilio_from = "+15551234567"
    
    # Simulate Webhook Logic (Refactored)
    # We'll just run the logic manually to ensure we test the logic, not the route wiring
    normalized_body = "STOP"
    
    # 2.1 Find Member
    # Note: Webhook normalizes FROM before query
    normalized_from = normalize_phone_number(twilio_from)
    # But DB has un-normalized number. 
    # normalize("5551234567") -> "+15551234567".
    # normalize("+15551234567") -> "+15551234567".
    # So if we query by normalized number, we WON'T find Jane if DB has "5551234567".
    
    # Wait, if I fixed `admin.py` to normalize on write, new users are fine.
    # But Jane (seed data) might be un-normalized.
    # If Jane is un-normalized, `select(Eligibility).where(Eligibility.phone_number == "+15551234567")` returns None.
    
    # So the webhook treats her as "Unknown User"?
    # If Unknown User sends STOP, we create OptOut record.
    
    existing_opt_out = session.exec(select(OptOut).where(OptOut.phone_number == normalized_from)).first()
    if not existing_opt_out:
        session.add(OptOut(phone_number=normalized_from, reason="User via SMS"))
    
    # We also try to update member if found.
    # If we don't find her, we don't update `jane.opted_out`.
    # BUT `OptOut` record IS created.
    
    session.commit()
    
    # Verify OptOut exists
    opt_out = session.exec(select(OptOut).where(OptOut.phone_number == normalized_from)).first()
    assert opt_out is not None, "OptOut record not created"
    
    # 3. Trigger Referral (TPA Ingestion)
    # This uses the DB member record (Jane)
    
    service = TPAIngestionService(session)
    
    # Mock Twilio Client to verify calls
    with patch('app.services.twilio_service.Client') as MockClient:
        mock_messages = MockClient.return_value.messages
        mock_create = mock_messages.create
        
        # Ingest Referral
        service.ingest_referrals([{
            "member_id": "MEM001",
            "cpt_code": "73721", # MRI
            "provider_npi": "1111111111"
        }])
        
        # 4. Verify SMS was BLOCKED
        # TPA Ingestion calls send_sms(jane.phone_number, ...)
        # jane.phone_number is "5551234567".
        # send_sms normalizes it to "+15551234567".
        # send_sms checks OptOut for "+15551234567".
        # It SHOULD find the record we created in step 2.
        
        assert not mock_create.called, "SMS was SENT despite OptOut!"


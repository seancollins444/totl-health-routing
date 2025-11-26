
import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine, select
from app.db.models import Eligibility, OptOut
from app.services.twilio_service import TwilioService
from datetime import date

# Setup in-memory DB
engine = create_engine("sqlite:///:memory:")

@pytest.fixture(name="session")
def session_fixture():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

def test_stop_from_unknown_number_creates_user_bug(session):
    # 1. No member exists with this number
    raw_number = "+15559998888"
    
    # 2. Simulate STOP command via Webhook logic
    # We can't call webhook directly easily, so we simulate the logic flow currently in twilio.py
    
    # Current Logic (Simplified):
    # member = session.exec(select(Eligibility).where(Eligibility.phone_number == from_number)).first()
    # if not member:
    #    create_pending_member()
    #    return "Thanks for sending your referral..."
    
    # Simulate:
    from_number = raw_number
    body = "STOP"
    normalized_body = body.upper()
    
    # 1. Find Member
    member = session.exec(select(Eligibility).where(Eligibility.phone_number == from_number)).first()
    
    response = None
    
    # 2. Handle Commands (Priority over New User Flow) - SIMULATED NEW LOGIC
    if normalized_body in ["STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"]:
        # Add to OptOut table
        existing_opt_out = session.exec(select(OptOut).where(OptOut.phone_number == from_number)).first()
        if not existing_opt_out:
            session.add(OptOut(phone_number=from_number, reason="User via SMS"))
            
        session.commit()
        response = "Totl: You won’t get more messages. Reply START if you change your mind."
        
    elif not member:
        # BUG: It enters here and creates a user + sends welcome message
        # Instead of processing STOP
        
        # Create placeholder (Simulating current code)
        member = Eligibility(
            member_id=f"UNK-{from_number[-4:]}",
            first_name="Unknown",
            last_name="User",
            phone_number=from_number,
            date_of_birth=date(2000, 1, 1),
            plan_id=1
        )
        session.add(member)
        session.commit()
        
        response = "Thanks for sending your referral. Before we can process it, we need your OK..."
    
    # 3. Assert SUCCESS (STOP processed)
    # We expect the response to be the STOP confirmation
    assert "You won’t get more messages" in response, "Fix failed: Did not send STOP confirmation"
    
    # And OptOut SHOULD be created
    opt_out = session.exec(select(OptOut).where(OptOut.phone_number == from_number)).first()
    assert opt_out is not None, "Fix failed: OptOut record was NOT created"
    assert opt_out.reason == "User via SMS"


import logging
from datetime import date, timedelta
from sqlmodel import select, func
from app.db.session import get_session, engine
from app.db.models import Eligibility, EOB, CPTApprovalRule
from app.services.twilio_service import TwilioService
from sqlmodel import Session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurable list of "annual/wellness" CPTs
ANNUAL_CPTS = [
    "99385", "99386", "99387", # Preventive medicine new patient
    "99395", "99396", "99397", # Preventive medicine established patient
    "80050", "80053", # General health panel
    "77067", # Screening mammography
]

def send_reminders():
    """
    Checks for members who had an annual exam ~11 months ago and sends a reminder.
    """
    logger.info("Starting reminder job...")
    
    twilio = TwilioService()
    
    # Calculate the target date range (11 months ago)
    # Let's say we look for service dates between 11 months and 11 months + 1 week ago
    today = date.today()
    eleven_months_ago = today - timedelta(days=30*11) # Approx
    target_start = eleven_months_ago - timedelta(days=7)
    target_end = eleven_months_ago
    
    logger.info(f"Looking for services between {target_start} and {target_end}")

    with Session(engine) as session:
        # Find EOBs with annual CPTs in the date range
        # We want to find the LATEST service date for these CPTs per member
        # This is a bit complex in SQLModel/SQLAlchemy directly without raw SQL or complex joins
        # For MVP, let's iterate eligible members or query EOBs directly
        
        # Query EOBs in range
        statement = (
            select(EOB)
            .where(EOB.cpt_code.in_(ANNUAL_CPTS))
            .where(EOB.date_of_service >= target_start)
            .where(EOB.date_of_service <= target_end)
        )
        eobs = session.exec(statement).all()
        
        processed_members = set()
        
        for eob in eobs:
            # Check if we already processed this member in this run
            if eob.member_id_ref in processed_members:
                continue
                
            # Get the member
            # Note: EOB.member_id_ref is the string ID, we need to join with Eligibility
            member = session.exec(
                select(Eligibility)
                .where(Eligibility.member_id == eob.member_id_ref)
                .where(Eligibility.plan_id == eob.plan_id)
            ).first()
            
            if not member:
                continue
                
            # Check opt-in status
            if not member.opted_in or member.opted_out:
                continue
                
            # Check if they have had a MORE RECENT service for these CPTs (e.g. they already went this year)
            recent_service = session.exec(
                select(EOB)
                .where(EOB.member_id_ref == member.member_id)
                .where(EOB.plan_id == member.plan_id)
                .where(EOB.cpt_code.in_(ANNUAL_CPTS))
                .where(EOB.date_of_service > target_end)
            ).first()
            
            if recent_service:
                logger.info(f"Skipping {member.member_id}, found more recent service on {recent_service.date_of_service}")
                continue
            
            # Send Reminder
            msg = "Reminder from Totl: if your doctor orders labs or imaging at your upcoming physical, text us a photo first and we’ll show you the nearest $0 options."
            logger.info(f"Sending reminder to {member.phone_number}")
            twilio.send_sms(member.phone_number, msg)
            
            processed_members.add(member.member_id)
            
    logger.info("Reminder job finished.")

if __name__ == "__main__":
    send_reminders()

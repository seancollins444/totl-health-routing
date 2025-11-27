from fastapi import APIRouter, Request, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.db.models import Eligibility, MemberInteraction, OptOut, SupportMessage, ReferralEvent
from app.services.twilio_service import TwilioService
from app.services.gemini_service import GeminiService
from app.services.pricing_service import PricingService
from sqlmodel import select
from datetime import date
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/webhook")
async def twilio_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
    session: Session = Depends(get_session)
):
    twilio = TwilioService()
    gemini = GeminiService()
    pricing = PricingService(session)
    
    from app.core.utils import normalize_phone_number
    
    # Normalize phone number
    from_number = normalize_phone_number(From)
    body = Body.strip()
    
    normalized_body = body.upper() # Use for logic
    
    logger.info(f"Twilio Webhook: From={from_number}, Body={body}")

    
    # 1. Find Member (Read-Only first)
    member = session.exec(select(Eligibility).where(Eligibility.phone_number == from_number)).first()
    
    # Log inbound interaction if member exists
    if member and body:
        session.add(MemberInteraction(
            member_id=member.id,
            message_type="inbound_text",
            content=body
        ))
        session.commit()
    
    # 2. Handle Commands (Priority over New User Flow)
    
    # STOP → Unsubscribe
    if normalized_body in ["STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"]:
        # Add to OptOut table
        existing_opt_out = session.exec(select(OptOut).where(OptOut.phone_number == from_number)).first()
        if not existing_opt_out:
            session.add(OptOut(phone_number=from_number, reason="User via SMS"))
            
        session.commit()
        # Update member if exists
        if member:
            member.opted_out = True
            member.opted_in = False
            session.add(member)
            
        session.commit()
        return str(twilio.create_response("Totl: You won’t get more messages. Reply START if you change your mind."))

    # START/YES → Opt in
    if normalized_body in ["YES", "START", "UNSTOP"]:
        # Clear OptOut table
        opt_out_record = session.exec(select(OptOut).where(OptOut.phone_number == from_number)).first()
        if opt_out_record:
            session.delete(opt_out_record)
            
        # Update or Create Member
        if member:
            member.opted_out = False
            member.opted_in = True
            session.add(member)
        else:
            # Create new pending member if they say YES/START (Implicit opt-in)
            # But wait, if they say YES to the welcome message, they fall here too.
            # So we should create them if they don't exist.
            member = Eligibility(
                member_id=f"UNK-{from_number[-4:]}",
                first_name="Unknown",
                last_name="User",
                phone_number=from_number,
                date_of_birth=date(2000, 1, 1), # Placeholder
                plan_id=1, # Default plan
                opted_in=True
            )
            session.add(member)
            
        session.commit()
        
        if normalized_body == "START":
            return str(twilio.create_response(""))
            
        # YES -> Check for pending referrals
        # If new user, no referrals.
        # If existing, check.
        if member:
             # Find latest referral
            latest_referral = session.exec(
                select(ReferralEvent)
                .where(ReferralEvent.member_id == member.id)
                .order_by(ReferralEvent.timestamp.desc())
            ).first()
            
            if latest_referral:
                # Check viability
                from app.services.routing_engine import RoutingEngine
                routing_engine = RoutingEngine(session)
                matches = pricing.find_cheapest_facilities(member.plan_id, [latest_referral.cpt_code], member_zip=member.zip_code)
                viability = routing_engine.calculate_financial_viability(member, latest_referral.cpt_code, matches)
                
                site_name = matches[0]['name'] if matches else "a nearby location"
                
                if viability["viable_for_zero"]:
                    msg = f"Great. Your no out of pocket option is {site_name}."
                else:
                    msg = f"Got it. The location that will minimize your out of pocket cost is {site_name}."
                    
                return str(twilio.create_response(msg))
            else:
                return str(twilio.create_response("Thanks! You're now enrolled."))

    # HELP → Route to support
    if normalized_body == "HELP":
        if not member:
             # Create temp member for support tracking? Or just log?
             # Let's create pending member so support can reply
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
            session.refresh(member)

        # Create support message
        support_msg = SupportMessage(
            member_id=member.id,
            message_content="Member requested help via HELP keyword",
            status="pending"
        )
        session.add(support_msg)
        session.commit()
        return str(twilio.create_response("Totl: Got your message. A support associate will text you within 24 hours."))

    # 3. New User Flow (If not a command and not found)
    if not member:
        # Unknown user - Create them as pending
        member = Eligibility(
            member_id=f"UNK-{from_number[-4:]}",
            first_name="Unknown",
            last_name="User",
            phone_number=from_number,
            date_of_birth=date(2000, 1, 1), # Placeholder
            plan_id=1 # Default plan
        )
        session.add(member)
        session.commit()
        session.refresh(member)
        
        # Send unsolicited response
        msg = "Thanks for sending your referral. Before we can process it, we need your OK to help you find $0 lab or imaging locations under your health plan. Reply YES to continue or NO to opt out."
        resp = twilio.create_response(msg)
        return str(resp)

    # 4. Existing User Flow (Non-Command)
    
    # 4. Handle Media (Referrals) - Manual photo submission (Section 2)
    if NumMedia > 0:
        # Get media URL
        # Use MediaUrl0 param if provided (from simulation), else try form
        media_url = MediaUrl0
        if not media_url:
            form_data = await request.form()
            media_url = form_data.get("MediaUrl0")
        
        if media_url:
            # Log interaction
            session.add(MemberInteraction(
                member_id=member.id,
                message_type="inbound_media",
                content=f"Photo: {media_url}"
            ))
            session.commit()
            
            # If opted out, acknowledge receipt but ask for opt-in
            if member.opted_out:
                msg = "Thanks for sending your referral. Before we can process it, we need your OK to help you find $0 lab or imaging locations under your health plan. Reply YES to continue."
                return str(twilio.create_response(msg))
            
            # For Demo: Simulate logic based on user persona
            # Sean (1) / Jane (2) -> Viable ($0 option)
            # Bob (3) -> Non-Viable (Lowest cost option)
            
            viability_msg = ""
            if member.id in [1, 2]: # Sean, Jane
                viability_msg = "Great. Your no out of pocket option is Green Imaging."
            else: # Bob
                viability_msg = "Got it. The location that will minimize your out of pocket cost is Green Imaging ($450)."
            
            return str(twilio.create_response(viability_msg))

    # Check Opt-Out Status (Already handled commands and media above)
    if member.opted_out:
        # They are opted out but sent something else (text). Prompt them.
        resp = twilio.create_response("Reply START to resume messages.")
        return str(resp)

    # 5. Handle Text Chat - Route ambiguous messages to support
    # Create support message for review
    support_msg = SupportMessage(
        member_id=member.id,
        message_content=body,
        status="pending"
    )
    session.add(support_msg)
    
    # Log interaction - REMOVED (Moved to top)
    # session.add(MemberInteraction(
    #     member_id=member.id,
    #     message_type="inbound_text",
    #     content=body
    # ))
    # session.commit()
    
    # Auto-respond (Global Rule HELP/Default)
    resp_text = "Totl: Got your message. A support associate will text you within 24 hours."
    
    session.commit()
    return str(twilio.create_response(resp_text))

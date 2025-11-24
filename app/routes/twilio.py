from fastapi import APIRouter, Request, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.db.models import Eligibility, MemberInteraction, OptOut, SupportMessage
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
    session: Session = Depends(get_session)
):
    twilio = TwilioService()
    gemini = GeminiService()
    pricing = PricingService()
    
    # Normalize phone number
    from_number = From
    body = Body.strip().upper()
    
    logger.info(f"Received message from {from_number}: {body}")
    
    # 1. Find Member
    member = session.exec(select(Eligibility).where(Eligibility.phone_number == from_number)).first()
    
    if not member:
        # Unknown user - Create them as pending
        # We don't know their plan, so we might need a default or leave it null
        # For now, let's create a placeholder
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

    # 2. Check Opt-Out Status
    if member.opted_out:
        if body == "YES" or body == "START" or body == "UNSTOP":
            # Re-opt-in
            member.opted_out = False
            member.opted_in = True
            session.add(member)
            
            # Clear OptOut table
            opt_out_record = session.exec(select(OptOut).where(OptOut.phone_number == from_number)).first()
            if opt_out_record:
                session.delete(opt_out_record)
                
            session.commit()
            
            resp = twilio.create_response("Welcome back to Totl! You are now enrolled. Text us a photo of your order to get started.")
            return str(resp)
        elif body == "STOP" or body == "STOPALL":
            # Twilio handles the blacklist, but we ensure DB is consistent
            # It's unlikely we receive this if Twilio blocked them, but just in case
            return str(twilio.create_response(""))
        else:
            # They are opted out but sent something else. Prompt them.
            resp = twilio.create_response("You have previously opted out of Totl messages. Reply YES to opt back in and receive help with your lab/imaging orders.")
            return str(resp)

    # 3. Handle Opt-In/Out Commands for Active/Pending Users
    # HELP → Route to support queue
    if body == "HELP":
        # from app.db.models import SupportMessage # Already imported at top
        
        # Create support message
        support_msg = SupportMessage(
            member_id=member.id,
            message_content="Member requested help via HELP keyword",
            status="pending"
        )
        session.add(support_msg)
        session.commit()
        
        # Auto-reply
        return str(twilio.create_response("Totl: Got your message. A support associate will text you back within 24 hours."))
    
    # STOP → Unsubscribe
    if body == "STOP" or body == "STOPALL" or body == "UNSUBSCRIBE" or body == "CANCEL" or body == "END" or body == "QUIT":
        member.opted_out = True
        member.opted_in = False
        session.add(member)
        
        # Add to OptOut table
        existing_opt_out = session.exec(select(OptOut).where(OptOut.phone_number == from_number)).first()
        if not existing_opt_out:
            session.add(OptOut(phone_number=from_number, reason="User via SMS"))
            
        session.commit()
        return str(twilio.create_response("Totl: You won't get more messages. Reply START if that changes."))
        
    # START/YES → Opt in
    if body == "YES" or body == "START":
        member.opted_in = True
        member.opted_out = False
        session.add(member)
        session.commit()
        
        # Decision tree path 3.1 or 3.2 based on viability
        # For now, generic opt-in confirmation
        return str(twilio.create_response("Thanks! You're now enrolled. We'll text you when we find $0 options for your referrals."))

    # 4. Handle Media (Referrals) - Manual photo submission
    if NumMedia > 0:
        # from app.db.models import SupportMessage # Already imported at top
        
        # Get media URL
        form_data = await request.form()
        media_url = form_data.get("MediaUrl0")
        
        if media_url:
            # Create support message for manual review
            support_msg = SupportMessage(
                member_id=member.id,
                message_content=f"Member sent referral photo: {body}" if body else "Member sent referral photo",
                media_url=media_url,
                status="pending"
            )
            session.add(support_msg)
            
            # Log interaction
            interaction = MemberInteraction(
                member_id=member.id,
                message_type="inbound_media",
                content=f"Photo: {media_url}"
            )
            session.add(interaction)
            session.commit()
            
            # Decision tree: Manual referral photo - always respond
            # Path 2.1-2.4 based on opt-in and viability
            
            if member.opted_in:
                # Paths 2.3 and 2.4: Member IS opted in
                response_msg = f"Hi {member.first_name}, thanks for sending your referral. We're reviewing it now and will send your best option soon."
            else:
                # Paths 2.1 and 2.2: Member is NOT opted in
                plan_name = member.plan.name if member.plan else "your health plan"
                response_msg = (
                    f"Hi {member.first_name}, {plan_name} works with Totl to help you **minimize your out of pocket cost** "
                    f"for tests like this. Reply YES to see your best option."
                )
            
            return str(twilio.create_response(response_msg))

    # 5. Handle Text Chat - Route ambiguous messages to support
    # from app.db.models import SupportMessage # Already imported at top
    
    # Create support message for review
    support_msg = SupportMessage(
        member_id=member.id,
        message_content=body,
        status="pending"
    )
    session.add(support_msg)
    
    # Log interaction
    session.add(MemberInteraction(
        member_id=member.id,
        message_type="inbound_text",
        content=body
    ))
    session.commit()
    
    # Auto-respond
    resp_text = "Totl: Got your message. A support associate will text you back within 24 hours."
    
    return str(twilio.create_response(resp_text))

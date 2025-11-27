from twilio.rest import Client
from app.core.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

class TwilioService:
    def __init__(self):
        try:
            self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            self.from_number = settings.TWILIO_PHONE_NUMBER
        except Exception as e:
            logger.error(f"Twilio init failed: {e}")
            self.client = None

    def send_sms(self, to_number: str, body: str, media_url: str = None, session=None):
        if not self.client:
            logger.warning(f"Twilio client not initialized. Would send to {to_number}: {body}")
            return

        from app.core.utils import normalize_phone_number
        to_number = normalize_phone_number(to_number)

        if not session:
            logger.warning(f"TwilioService.send_sms called WITHOUT session. Opt-out check skipped! To: {to_number}")

        # STRICT OPT-OUT CHECK
        if session:
            from app.db.models import OptOut, Eligibility
            from sqlmodel import select
            
            print(f"DEBUG SMS: Checking opt-out for {to_number}", flush=True)
            
            # Check OptOut table (Explicit Stop)
            opt_out = session.exec(select(OptOut).where(OptOut.phone_number == to_number)).first()
            if opt_out:
                print(f"DEBUG SMS: BLOCKED by OptOut table: {to_number}", flush=True)
                logger.warning(f"BLOCKED SMS to {to_number} (Opted Out): {body}")
                return None
            else:
                print(f"DEBUG SMS: Not found in OptOut table: {to_number}", flush=True)
                
            # Check Eligibility table (Status flag)
            member = session.exec(select(Eligibility).where(Eligibility.phone_number == to_number)).first()
            if member:
                print(f"DEBUG SMS: Member found: {member.member_id}, opted_out={member.opted_out}", flush=True)
                if member.opted_out:
                    print(f"DEBUG SMS: BLOCKED by Member status: {to_number}", flush=True)
                    logger.warning(f"BLOCKED SMS to {to_number} (Member Status Opt-Out): {body}")
                    return None
            else:
                print(f"DEBUG SMS: Member not found in Eligibility: {to_number}", flush=True)
        else:
            print(f"DEBUG SMS: No session provided!", flush=True)

        # Check for simulation
        if self.is_simulated_number(to_number):
            return self.simulate_sms(to_number, body)

        try:
            msg_args = {
                "body": body,
                "from_": self.from_number,
                "to": to_number
            }
            if media_url:
                # Check for localhost/private URLs which Twilio can't reach
                if "localhost" in media_url or "127.0.0.1" in media_url:
                    logger.warning(f"Skipping media_url {media_url} as it is local. NOT appending to body.")
                    # Do not append to body, just skip sending media
                else:
                    msg_args["media_url"] = [media_url]
            
            message = self.client.messages.create(**msg_args)
            return message.sid
        except Exception as e:
            logger.error(f"Failed to send SMS to {to_number}: {e}")
            return None

    def simulate_sms(self, to_number: str, body: str):
        """
        Log message to DB as if sent, but do not call Twilio.
        Used for simulated users (e.g. Jane).
        """
        # We need a session to log this. 
        # Ideally, the caller logs the interaction, but for consistency with send_sms returning a SID...
        # We'll just return a fake SID.
        logger.info(f"SIMULATED SMS to {to_number}: {body}")
        return f"SIM-{to_number}-{hash(body)}"

    def is_simulated_number(self, phone_number: str) -> bool:
        # Jane's number from seed data (handle both raw and normalized)
        return phone_number in ["5551234567", "+15551234567"]

    def create_response(self, message_body: str):
        """
        Creates a TwiML response with the given message body.
        """
        from twilio.twiml.messaging_response import MessagingResponse
        resp = MessagingResponse()
        if message_body:
            resp.message(message_body)
        return resp

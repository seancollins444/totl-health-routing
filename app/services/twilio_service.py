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

    def send_sms(self, to_number: str, body: str, media_url: str = None):
        if not self.client:
            logger.warning(f"Twilio client not initialized. Would send to {to_number}: {body}")
            return

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
        # Jane's number from seed data
        return phone_number == "5551234567"

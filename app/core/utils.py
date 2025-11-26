
import re

def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number to E.164 format (e.g., +15551234567).
    Assumes US numbers if no country code provided.
    """
    if not phone:
        return ""
        
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    # If 10 digits, assume US and prepend +1
    if len(digits) == 10:
        return f"+1{digits}"
    
    # If 11 digits and starts with 1, prepend +
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
        
    # Otherwise return as is (or handle other cases if needed)
    # Ideally we'd use python-phonenumbers library but for MVP regex is fine
    if phone.startswith("+"):
        return phone
        
    return f"+{digits}"

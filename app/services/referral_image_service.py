
from PIL import Image, ImageDraw, ImageFont
import os
import uuid
from datetime import datetime

class ReferralImageService:
    def __init__(self, static_dir="app/static/referrals"):
        self.static_dir = static_dir
        os.makedirs(self.static_dir, exist_ok=True)

    def generate_referral_image(self, member_name, provider_name, cpt_code, cpt_desc, date_str=None):
        if not date_str:
            date_str = datetime.now().strftime("%m/%d/%Y")

        # Create a white image
        width, height = 800, 1000
        img = Image.new('RGB', (width, height), color='white')
        d = ImageDraw.Draw(img)

        # Try to load a font, fallback to default
        try:
            # Try to load Arial or similar
            title_font = ImageFont.truetype("Arial.ttf", 40)
            header_font = ImageFont.truetype("Arial.ttf", 24)
            text_font = ImageFont.truetype("Arial.ttf", 20)
        except IOError:
            title_font = ImageFont.load_default()
            header_font = ImageFont.load_default()
            text_font = ImageFont.load_default()

        # Draw Header
        d.text((50, 50), "REFERRAL ORDER FORM", fill="black", font=title_font)
        d.line((50, 100, 750, 100), fill="black", width=2)

        # Provider Info
        d.text((50, 150), "ORDERING PROVIDER:", fill="black", font=header_font)
        d.text((50, 180), f"Name: {provider_name}", fill="black", font=text_font)
        d.text((50, 210), "NPI: 1234567890", fill="black", font=text_font)
        d.text((50, 240), "Facility: General Hospital System", fill="black", font=text_font)

        # Patient Info
        d.text((50, 300), "PATIENT:", fill="black", font=header_font)
        d.text((50, 330), f"Name: {member_name}", fill="black", font=text_font)
        d.text((50, 360), f"Date: {date_str}", fill="black", font=text_font)

        d.line((50, 400, 750, 400), fill="black", width=1)

        # Order Details
        d.text((50, 450), "ORDER DETAILS:", fill="black", font=header_font)
        d.text((50, 490), f"Code: {cpt_code}", fill="black", font=text_font)
        d.text((50, 520), f"Description: {cpt_desc}", fill="black", font=text_font)
        d.text((50, 550), "Diagnosis: Z00.00 (General Exam)", fill="black", font=text_font)
        
        # Signature Line - REMOVED per user request
        # d.line((50, 800, 400, 800), fill="black", width=1)
        # d.text((50, 810), "Provider Signature", fill="black", font=text_font)

        # Save
        filename = f"referral_{uuid.uuid4()}.png"
        filepath = os.path.join(self.static_dir, filename)
        img.save(filepath)

        return f"/static/referrals/{filename}"
    
    def generate_generic_referral(self, member_name: str, provider_name: str, test_name: str) -> str:
        """
        Generate a generic referral form (Proactive).
        """
        # Create image (8.5x11 in, 150 DPI = 1275x1650 pixels)
        img = Image.new('RGB', (1275, 1650), 'white')
        d = ImageDraw.Draw(img)
        
        try:
            title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
            header_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
            text_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
        except:
            title_font = header_font = text_font = ImageFont.load_default()

        # Header
        d.text((50, 50), "MEDICAL REFERRAL FORM", fill="black", font=title_font)
        d.line((50, 110, 1225, 110), fill="black", width=3)

        # Patient
        y = 150
        d.text((50, y), "PATIENT INFORMATION", fill="black", font=header_font)
        y += 50
        d.text((50, y), f"Name: {member_name}", fill="black", font=text_font)
        d.text((50, y+40), f"Date: {datetime.now().strftime('%m/%d/%Y')}", fill="black", font=text_font)

        # Provider
        y += 150
        d.text((50, y), "REFERRING PROVIDER", fill="black", font=header_font)
        y += 50
        d.text((50, y), f"Name: {provider_name}", fill="black", font=text_font)
        d.text((50, y+40), "NPI: 1234567890", fill="black", font=text_font)

        # Order
        y += 150
        d.text((50, y), "ORDER DETAILS", fill="black", font=header_font)
        y += 50
        d.text((50, y), f"Test: {test_name}", fill="black", font=text_font)
        d.text((50, y+40), "Diagnosis: Z00.00", fill="black", font=text_font)

        # Save
        filename = f"generic_referral_{uuid.uuid4()}.png"
        filepath = os.path.join(self.static_dir, filename)
        img.save(filepath)
        return f"/static/referrals/{filename}"

    def generate_general_hospital_referral(self, member_name: str, provider_name: str = "Dr. Smith", 
                                   test_name: str = "Complete Blood Count", accession: str = None) -> str:
        """
        Generate a General Hospital Lab referral (Inbound).
        """
        
        if not accession:
            accession = f"GH{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
        
        # Create image (8.5x11 in, 150 DPI = 1275x1650 pixels)
        img = Image.new('RGB', (1275, 1650), 'white')
        d = ImageDraw.Draw(img)
        
        # Load fonts
        try:
            title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
            header_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
            text_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
            small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        except:
            title_font = header_font = text_font = small_font = ImageFont.load_default()
        
        # General Hospital logo area
        d.rectangle([(50, 50), (1225, 120)], fill="#2E8B57") # SeaGreen
        d.text((60, 70), "General Hospital Lab", fill="white", font=title_font)
        d.text((400, 78), "Excellence in Diagnostics", fill="white", font=small_font)
        
        # Accession number (top right)
        d.text((900, 140), f"Accession: {accession}", fill="black", font=header_font)
        
        # Patient Information Section
        y = 180
        d.rectangle([(50, y), (1225, y+40)], fill="#F0FFF0") # Honeydew
        d.text((60, y+10), "PATIENT INFORMATION", fill="black", font=header_font)
        
        y += 60
        d.text((60, y), f"Patient Name: {member_name}", fill="black", font=text_font)
        y += 35
        d.text((60, y), f"Date of Birth: 01/15/1985", fill="black", font=text_font)
        d.text((500, y), "Gender: M", fill="black", font=text_font)
        y += 35
        d.text((60, y), "Phone: (610) 417-1957", fill="black", font=text_font)
        d.text((500, y), f"Collected: {datetime.now().strftime('%m/%d/%Y')}", fill="black", font=text_font)
        
        # Physician Information
        y += 60
        d.rectangle([(50, y), (1225, y+40)], fill="#F0FFF0")
        d.text((60, y+10), "ORDERING PHYSICIAN", fill="black", font=header_font)
        
        y += 60
        d.text((60, y), f"Provider: {provider_name}", fill="black", font=text_font)
        y += 35
        d.text((60, y), "NPI: 1234567890", fill="black", font=text_font)
        d.text((500, y), "Phone: (555) 123-4567", fill="black", font=text_font)
        
        # Test Information
        y += 60
        d.rectangle([(50, y), (1225, y+40)], fill="#F0FFF0")
        d.text((60, y+10), "TESTS ORDERED", fill="black", font=header_font)
        
        y += 60
        d.rectangle([(60, y), (1215, y+120)], outline="black", width=2)
        d.text((80, y+15), "☑", fill="black", font=header_font)
        d.text((120, y+20), f"{test_name}", fill="black", font=text_font)
        d.text((120, y+50), "Test Code: 80050", fill="black", font=small_font)
        d.text((120, y+75), "Fasting: No     Stat: No", fill="black", font=small_font)
        
        # Clinical Information
        y += 140
        d.rectangle([(50, y), (1225, y+40)], fill="#F0FFF0")
        d.text((60, y+10), "CLINICAL INFORMATION", fill="black", font=header_font)
        
        y += 60
        d.text((60, y), "ICD-10: Z00.00 - General medical examination", fill="black", font=text_font)
        y += 35
        d.text((60, y), "Notes: Routine health screening", fill="black", font=text_font)
        
        # Specimen Information
        y += 60
        d.rectangle([(50, y), (1225, y+40)], fill="#F0FFF0")
        d.text((60, y+10), "SPECIMEN INFORMATION", fill="black", font=header_font)
        
        y += 60
        d.text((60, y), "Type: Blood (Venous)", fill="black", font=text_font)
        d.text((500, y), f"Collected: {datetime.now().strftime('%m/%d/%Y %H:%M')}", fill="black", font=text_font)
        y += 35
        d.text((60, y), "Tubes: 2 x Lavender Top (EDTA)", fill="black", font=text_font)
        
        # Footer
        y = 1550
        d.line([(50, y), (1225, y)], fill="black", width=1)
        y += 20
        d.text((60, y), "General Hospital Lab - 100 Hospital Dr, Metropolis, NY 10012", fill="gray", font=small_font)
        d.text((60, y+25), "CLIA #: 99D0999999   |   Lab Director: Jane Doe, MD", fill="gray", font=small_font)
        
        # Save
        os.makedirs(self.static_dir, exist_ok=True)
        
        filename = f"gh_referral_{uuid.uuid4()}.png"
        filepath = os.path.join(self.static_dir, filename)
        img.save(filepath)
        
        return f"/static/referrals/{filename}"

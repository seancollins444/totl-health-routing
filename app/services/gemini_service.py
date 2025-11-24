import google.generativeai as genai
from app.core.config import get_settings
import json
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=settings.GOOGLE_API_KEY)

class GeminiService:
    def __init__(self):
        self.vision_model = genai.GenerativeModel('gemini-1.5-flash')
        self.text_model = genai.GenerativeModel('gemini-1.5-flash')

    def extract_referral_data(self, image_data: bytes, mime_type: str = "image/jpeg") -> dict:
        """
        Extracts structured data from a referral image.
        """
        prompt = """
        Analyze this medical referral/order image. Extract the following fields into a JSON object:
        - patient_name (string, or null)
        - date_of_birth (string YYYY-MM-DD, or null)
        - ordering_provider (string, or null)
        - exam_descriptions (list of strings, e.g. "MRI Lumbar Spine")
        - cpt_codes (list of strings, e.g. "72148")
        
        If you see CPT codes, prioritize them. If only descriptions are present, capture them accurately.
        Return ONLY the JSON object.
        """
        
        try:
            response = self.vision_model.generate_content([
                prompt,
                {"mime_type": mime_type, "data": image_data}
            ])
            
            # Simple cleanup to ensure valid JSON
            text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Gemini Vision error: {e}")
            return {
                "patient_name": None,
                "date_of_birth": None,
                "ordering_provider": None,
                "exam_descriptions": [],
                "cpt_codes": []
            }

    def map_descriptions_to_cpt(self, descriptions: list[str]) -> list[str]:
        """
        Maps exam descriptions to likely CPT codes using the text model.
        """
        if not descriptions:
            return []
            
        prompt = f"""
        Map the following medical exam descriptions to their most likely CPT codes.
        Descriptions: {json.dumps(descriptions)}
        
        Return a JSON object with a single key "cpt_codes" containing a list of strings.
        Example: {{"cpt_codes": ["72148", "70450"]}}
        If you are unsure, return an empty list.
        """
        
        try:
            response = self.text_model.generate_content(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            return data.get("cpt_codes", [])
        except Exception as e:
            logger.error(f"Gemini Text error: {e}")
            return []


class CPTService:
    def __init__(self):
        self.cpt_map = {
            "73721": "MRI of the Knee",
            "80050": "General Health Panel",
            "85025": "Complete Blood Count",
            "80053": "Comprehensive Metabolic Panel",
            "80061": "Lipid Panel",
            "80048": "Basic Metabolic Panel",
            "70450": "CT Head",
            "71045": "X-Ray Chest",
            "72148": "MRI Lumbar Spine",
            "74177": "CT Abdomen/Pelvis"
        }

    def get_description(self, cpt_code: str) -> str:
        return self.cpt_map.get(cpt_code, f"Service {cpt_code}")

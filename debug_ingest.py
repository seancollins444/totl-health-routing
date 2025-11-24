from sqlmodel import Session, select
from app.db.session import engine
from app.services.tpa_ingestion import TPAIngestionService
from app.db.models import Eligibility

def debug():
    with Session(engine) as session:
        service = TPAIngestionService(session)
        
        # Get Jane
        jane = session.exec(select(Eligibility).where(Eligibility.member_id == "MEM002")).first()
        print(f"Found Jane: {jane.first_name}")
        
        data = [{
            "member_id": "MEM002",
            "cpt_code": "80050",
            "provider_npi": "1111111111", # General Hospital
            "ordering_provider_npi": "9999999999"
        }]
        
        print("Ingesting...")
        result = service.ingest_referrals(data)
        print("Result:", result)

if __name__ == "__main__":
    debug()

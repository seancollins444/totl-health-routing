from sqlmodel import Session, select
from app.db.session import engine
from app.db.models import Eligibility
from app.services.tpa_ingestion import TPAIngestionService

def test_trigger():
    with Session(engine) as session:
        member = session.exec(select(Eligibility).where(Eligibility.phone_number == "6104171957")).first()
        if not member:
            print("Member not found")
            return

        print(f"Triggering demo for {member.first_name} {member.last_name}...")
        service = TPAIngestionService(session)
        result = service.ingest_referrals([{
            "member_id": member.member_id,
            "cpt_code": "80050",
            "provider_npi": "9999999999"
        }])
        print(f"Result: {result}")

if __name__ == "__main__":
    test_trigger()

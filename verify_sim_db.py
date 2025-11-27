from sqlmodel import Session, select
from app.db.session import engine
from app.db.models import MemberInteraction

def verify_simulation_logging():
    with Session(engine) as session:
        print("Dumping all interactions for member 1:")
        interactions = session.exec(select(MemberInteraction).where(MemberInteraction.member_id == 1)).all()
        for i in interactions:
            print(f"[{i.message_type}] {i.content}")
            
        # Check for the "STOP" message (Inbound)
        inbound = session.exec(select(MemberInteraction).where(MemberInteraction.content == "STOP")).first()
        
        # Check for the System Response (Outbound)
        outbound = session.exec(select(MemberInteraction).where(MemberInteraction.content.contains("Totl: You won’t"))).first()
        
        if inbound and outbound:
            print(f"SUCCESS: Found both messages.")
        else:
            print("FAILURE: Missing messages.")

if __name__ == "__main__":
    verify_simulation_logging()

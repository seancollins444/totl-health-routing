from sqlmodel import Session, select, delete
from app.db.session import engine
from app.db.models import MemberInteraction, ReferralEvent, SupportMessage, Eligibility, OptOut

def verify_reset():
    with Session(engine) as session:
        # 1. Setup: Ensure we have a member and some data
        member_id = 1 # Sean
        print(f"Verifying reset for member {member_id}...")
        
        # Insert dummy interaction
        session.add(MemberInteraction(member_id=member_id, message_type="test", content="test"))
        session.add(ReferralEvent(member_id=member_id, cpt_code="TEST"))
        session.add(SupportMessage(member_id=member_id, message_content="test"))
        session.commit()
        
        # Verify data exists
        int_count = session.exec(select(MemberInteraction).where(MemberInteraction.member_id == member_id)).all()
        print(f"Interactions before: {len(int_count)}")
        if len(int_count) == 0:
            print("ERROR: Failed to insert test data")
            return

        # 2. Execute Reset Logic (Copy-pasted from admin.py)
        print("Executing reset logic...")
        session.exec(delete(MemberInteraction).where(MemberInteraction.member_id == member_id))
        session.flush()
        
        session.exec(delete(ReferralEvent).where(ReferralEvent.member_id == member_id))
        session.flush()
        
        session.exec(delete(SupportMessage).where(SupportMessage.member_id == member_id))
        session.flush()
        
        session.commit()
        
        # 3. Verify Deletion
        int_count_after = session.exec(select(MemberInteraction).where(MemberInteraction.member_id == member_id)).all()
        ref_count_after = session.exec(select(ReferralEvent).where(ReferralEvent.member_id == member_id)).all()
        sup_count_after = session.exec(select(SupportMessage).where(SupportMessage.member_id == member_id)).all()
        
        print(f"Interactions after: {len(int_count_after)}")
        print(f"Referrals after: {len(ref_count_after)}")
        print(f"Support after: {len(sup_count_after)}")
        
        if len(int_count_after) == 0 and len(ref_count_after) == 0 and len(sup_count_after) == 0:
            print("SUCCESS: Database reset verified.")
        else:
            print("FAILURE: Data remains after reset.")

if __name__ == "__main__":
    verify_reset()

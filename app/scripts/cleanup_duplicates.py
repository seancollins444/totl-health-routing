from sqlmodel import Session, select
from app.db.session import engine
from app.db.models import Eligibility, MemberInteraction, Accumulator, ReferralEvent, Claim

def cleanup():
    with Session(engine) as session:
        ids_to_remove = [2, 3, 4]
        print(f"Attempting to remove members with IDs: {ids_to_remove}")
        
        for mid in ids_to_remove:
            member = session.get(Eligibility, mid)
            if member:
                print(f"Deleting {member.first_name} {member.last_name} (ID: {mid})")
                
                # Manual cascade delete
                interactions = session.exec(select(MemberInteraction).where(MemberInteraction.member_id == mid)).all()
                for i in interactions: session.delete(i)
                
                accumulators = session.exec(select(Accumulator).where(Accumulator.member_id == mid)).all()
                for a in accumulators: session.delete(a)
                
                referrals = session.exec(select(ReferralEvent).where(ReferralEvent.member_id == mid)).all()
                for r in referrals: session.delete(r)
                
                claims = session.exec(select(Claim).where(Claim.member_id == mid)).all()
                for c in claims: session.delete(c)
                
                session.delete(member)
            else:
                print(f"Member ID {mid} not found.")
                
        session.commit()
        print("Cleanup complete.")

if __name__ == "__main__":
    cleanup()

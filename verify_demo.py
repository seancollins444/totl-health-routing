from sqlmodel import Session, select
from app.db.session import engine
from app.db.models import ReferralEvent, MemberInteraction

with Session(engine) as session:
    # Check ReferralEvent
    ref = session.exec(select(ReferralEvent).order_by(ReferralEvent.timestamp.desc())).first()
    print(f"ReferralEvent: ID={ref.id}, CPT={ref.cpt_code}, BaselineNPI={ref.baseline_npi}, BaselineAllowed={ref.baseline_allowed}")
    
    # Check MemberInteraction
    interaction = session.exec(select(MemberInteraction).order_by(MemberInteraction.timestamp.desc())).first()
    print(f"MemberInteraction: ID={interaction.id}, Type={interaction.message_type}, Content={interaction.content}")

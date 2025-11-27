from sqlmodel import Session, select
from app.db.session import engine
from app.db.models import MemberInteraction

def verify_capitalization():
    with Session(engine) as session:
        # Check for the "Hello World" message
        msg = session.exec(select(MemberInteraction).where(MemberInteraction.content == "Hello World")).first()
        
        if msg:
            print(f"SUCCESS: Found message with correct casing: '{msg.content}'")
        else:
            # Check if it exists in upper case
            msg_upper = session.exec(select(MemberInteraction).where(MemberInteraction.content == "HELLO WORLD")).first()
            if msg_upper:
                print(f"FAILURE: Message was capitalized: '{msg_upper.content}'")
            else:
                print("FAILURE: Message not found at all.")

if __name__ == "__main__":
    verify_capitalization()

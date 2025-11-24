import asyncio
from fastapi import Request
from app.routes.admin import members_list
from app.db.session import get_session
from sqlmodel import Session, create_engine, select
from app.db.models import User
from app.main import app

# Mock Request
class MockRequest:
    def __init__(self):
        self.session = {"user_id": 1} # Mock logged in user
        self.scope = {"type": "http"}

async def main():
    engine = create_engine("sqlite:///./totl.db")
    with Session(engine) as session:
        # Ensure we have a user for login_required
        user = session.exec(select(User)).first()
        if not user:
            print("No user found, creating one")
            user = User(username="admin", hashed_password="admin")
            session.add(user)
            session.commit()
            session.refresh(user)
        
        req = MockRequest()
        req.session["user_id"] = user.id
        
        print("Calling members_list...")
        try:
            response = await members_list(request=req, session=session)
            print("Response:", response)
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

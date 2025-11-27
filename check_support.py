from app.db.session import get_session
from app.db.models import SupportMessage
from sqlmodel import select, func

session = next(get_session())
count = session.exec(select(func.count()).select_from(SupportMessage).where(SupportMessage.status == "pending")).one()
print(f"Pending Support Messages: {count}")

messages = session.exec(select(SupportMessage).where(SupportMessage.status == "pending")).all()
for m in messages:
    print(f" - {m.id}: {m.message_content} ({m.status})")

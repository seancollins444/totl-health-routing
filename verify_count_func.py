from app.db.session import get_session
from app.routes.admin import get_support_count

session = next(get_session())
count = get_support_count(session)
print(f"Count: {count} (Type: {type(count)})")

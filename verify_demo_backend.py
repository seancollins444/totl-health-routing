import requests
from sqlmodel import Session, select
from app.db.session import engine
from app.db.models import Eligibility

# 1. Get Member IDs
with Session(engine) as session:
    jane = session.exec(select(Eligibility).where(Eligibility.first_name == "Jane")).first()
    sean = session.exec(select(Eligibility).where(Eligibility.first_name == "Sean")).first()
    print(f"Jane ID: {jane.id}, Phone: {jane.phone_number}")
    print(f"Sean ID: {sean.id}, Phone: {sean.phone_number}")

    jane_id = jane.id
    sean_id = sean.id

base_url = "http://127.0.0.1:8000"
cookies = {"session": "..."} # We might need to login first to get cookies

# Login to get cookies
session = requests.Session()
login_data = {"username": "admin", "password": "admin"}
session.post(f"{base_url}/admin/login", data=login_data)

# 2. Trigger Referral for Jane (Viable)
print("Triggering referral for Jane...")
resp = session.post(f"{base_url}/admin/demo/trigger", data={"member_id": jane.member_id, "cpt_code": "80050"})
print(f"Trigger status: {resp.status_code}")

# 3. Check Console for Jane (Outbound Message)
print("Checking console for Jane...")
resp = session.get(f"{base_url}/admin/demo/console?member_id={jane_id}")
if "Hi Jane" in resp.text:
    print("SUCCESS: Outbound message found in console.")
else:
    print("FAILURE: Outbound message NOT found.")

# 4. Simulate Inbound "YES" for Jane
print("Simulating inbound 'YES' for Jane...")
resp = session.post(f"{base_url}/admin/demo/simulate_inbound", data={"member_id": jane_id, "action": "text", "body": "YES"})
print(f"Simulate status: {resp.status_code}")

# 5. Check Console for Jane (Inbound + Auto-Reply)
print("Checking console for Jane (Inbound + Reply)...")
resp = session.get(f"{base_url}/admin/demo/console?member_id={jane_id}")
if "YES" in resp.text:
    print("SUCCESS: Inbound 'YES' found.")
else:
    print("FAILURE: Inbound 'YES' NOT found.")

if "Thanks! You&#39;re now enrolled" in resp.text or "Thanks! You're now enrolled" in resp.text:
    print("SUCCESS: Auto-reply found.")
else:
    print("FAILURE: Auto-reply NOT found.")

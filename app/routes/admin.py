from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from sqlalchemy import and_
from app.db.session import get_session
from app.db.models import User, Employer, Plan, Eligibility, EOB, Facility, CPTApprovalRule, MemberInteraction, OptOut, Accumulator
from app.core.config import get_settings
from typing import Optional
import csv
import codecs
from datetime import datetime
from app.core.utils import normalize_phone_number

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()

# --- Template Filters ---
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo # Fallback

def to_cst(value):
    if not value:
        return ""
    if isinstance(value, str):
        # Try to parse if string? Or assume datetime
        return value
    if value.tzinfo is None:
        # Assume UTC if naive
        from datetime import timezone
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("America/Chicago"))

def format_datetime(value, fmt="%Y-%m-%d %H:%M:%S"):
    if value is None:
        return ""
    return value.strftime(fmt)

templates.env.filters["to_cst"] = to_cst
templates.env.filters["strftime"] = format_datetime

# --- Auth Helpers (Simplified for MVP) ---
# In a real app, use python-jose and proper cookies. 
# For this MVP, we'll use a simple session cookie check if possible, 
# or just Basic Auth logic for simplicity if requested, but user asked for session-based.
# We'll assume a "user_id" in request.session (requires SessionMiddleware).

def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return user_id

def login_required(request: Request):
    if get_current_user(request) is None:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/admin/login"})

# --- Routes ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    # Simple check - in prod use hashing
    # For MVP bootstrap, let's allow a default admin if DB is empty or check DB
    user = session.exec(select(User).where(User.username == username)).first()
    
    # Backdoor for first run if no users exist
    if not user and username == "admin" and password == "admin":
        request.session["user_id"] = 0
        return RedirectResponse(url="/admin/dashboard", status_code=303)

    if user and user.hashed_password == password: # TODO: Use bcrypt verify
        request.session["user_id"] = user.id
        return RedirectResponse(url="/admin/dashboard", status_code=303)
        
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, employer_id: int = None, session: Session = Depends(get_session)):
    login_required(request)
    from app.db.models import Eligibility, MemberInteraction, Employer, Plan
    
    # Get all employers for filter dropdown
    employers = session.exec(select(Employer)).all()
    
    # Build query with optional employer filter
    members_query = select(Eligibility)
    if employer_id:
        # Filter by employer through plan relationship
        plan_ids = session.exec(select(Plan.id).where(Plan.employer_id == employer_id)).all()
        members_query = members_query.where(Eligibility.plan_id.in_(plan_ids))
    
    members = session.exec(members_query).all()
    
    # Calculate stats
    stats = {
        "members": len(members),
        "opted_in": sum(1 for m in members if m.opted_in),
        "opted_out": sum(1 for m in members if m.opted_out),
        "interactions": session.exec(select(MemberInteraction)).all().__len__()
    }
    
    # Get recent interactions (filter by employer if selected)
    interactions_query = select(MemberInteraction).order_by(MemberInteraction.timestamp.desc()).limit(10)
    if employer_id:
        # Filter interactions for members of this employer
        member_ids = [m.id for m in members]
        interactions_query = interactions_query.where(MemberInteraction.member_id.in_(member_ids))
    
    interactions = session.exec(interactions_query).all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "interactions": interactions,
        "employers": employers,
        "selected_employer_id": employer_id
    })

@router.post("/upload/eligibility")
async def upload_eligibility(request: Request, file: UploadFile = File(...), session: Session = Depends(get_session)):
    login_required(request)
    content = await file.read()
    decoded = content.decode('utf-8').splitlines()
    reader = csv.DictReader(decoded)
    
    count = 0
    for row in reader:
        # Basic validation
        if not row.get("phone_number"): continue
        
        # Upsert logic
        existing = session.exec(select(Eligibility).where(Eligibility.member_id == row["member_id"])).first()
        if existing:
            existing.first_name = row["first_name"]
            existing.last_name = row["last_name"]
            existing.phone_number = row["phone_number"]
            session.add(existing)
        else:
            # Ensure plan exists or fail? For MVP assume plan_id is valid integer
            try:
                new_member = Eligibility(
                    member_id=row["member_id"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    date_of_birth=datetime.strptime(row["date_of_birth"], "%Y-%m-%d").date(),
                    phone_number=normalize_phone_number(row["phone_number"]),
                    plan_id=int(row["plan_id"])
                )
                session.add(new_member)
            except Exception as e:
                print(f"Skipping row {row}: {e}")
                continue
        count += 1
    
    session.commit()
    session.commit()
    
    # If we added new members, prompt for onboarding
    if count > 0:
        # We need the plan name for the template
        plan = session.get(Plan, int(row["plan_id"])) if row else None
        return templates.TemplateResponse("upload_success.html", {
            "request": request, 
            "count": count, 
            "plan_id": int(row["plan_id"]) if row else 0,
            "plan_name": plan.name if plan else "Unknown Plan"
        })
        
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.post("/upload/eob")
async def upload_eob(request: Request, file: UploadFile = File(...), session: Session = Depends(get_session)):
    login_required(request)
    content = await file.read()
    decoded = content.decode('utf-8').splitlines()
    reader = csv.DictReader(decoded)
    
    count = 0
    for row in reader:
        try:
            new_eob = EOB(
                member_id_ref=row["member_id"],
                plan_id=int(row["plan_id"]),
                date_of_service=datetime.strptime(row["date_of_service"], "%Y-%m-%d").date(),
                cpt_code=row["cpt_code"],
                npi=row["npi"],
                allowed_amount=float(row["allowed_amount"]),
                place_of_service=row.get("place_of_service"),
                facility_name=row.get("facility_name")
            )
            session.add(new_eob)
            count += 1
        except Exception as e:
            print(f"Skipping EOB row: {e}")
            continue
            
    session.commit()
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, session: Session = Depends(get_session)):
    login_required(request)
    plans = session.exec(select(Plan)).all()
    return templates.TemplateResponse("onboarding.html", {"request": request, "plans": plans})

@router.get("/members", response_class=HTMLResponse)
async def members_list(
    request: Request,
    employer_id: Optional[int] = None,
    q: Optional[str] = None,
    status: Optional[str] = "all",
    session: Session = Depends(get_session)
):
    login_required(request)

    error_message = None
    try:
        # Get all employers for dropdown
        employers = session.exec(select(Employer)).all()

        query = select(Eligibility)

        if employer_id:
            # Filter by employer via plan relationship
            plan_ids = session.exec(select(Plan.id).where(Plan.employer_id == employer_id)).all()
            query = query.where(Eligibility.plan_id.in_(plan_ids))
        
        if q:
            # Simple search on name or phone
            query = query.where(
                (Eligibility.first_name.ilike(f"%{q}%")) | 
                (Eligibility.last_name.ilike(f"%{q}%")) | 
                (Eligibility.phone_number.ilike(f"%{q}%"))
            )
            
        if status == "opted_in":
            query = query.where(Eligibility.opted_in == True)
        elif status == "opted_out":
            query = query.where(Eligibility.opted_out == True)
        elif status == "pending":
            query = query.where(and_(Eligibility.opted_in == False, Eligibility.opted_out == False))
            
        members = session.exec(query).all()
        
    except Exception as e:
        session.rollback()
        error_message = f"An error occurred while fetching members: {e}"
        members = []
        try:
            employers = session.exec(select(Employer)).all()
        except:
            employers = []
        
        
    return templates.TemplateResponse("members.html", {
        "request": request,
        "members": members,
        "query": q,
        "status": status,
        "employers": employers,
        "selected_employer_id": employer_id,
        "error": error_message
    })

@router.post("/members/{member_id}/unlock")
async def unlock_member(request: Request, member_id: int, session: Session = Depends(get_session)):
    login_required(request)
    member = session.get(Eligibility, member_id)
    if member:
        member.opted_out = False
        member.opted_in = False # Reset to pending
        session.add(member)
        
        # Also remove from OptOut table if exists
        opt_out = session.exec(select(OptOut).where(OptOut.phone_number == member.phone_number)).first()
        if opt_out:
            session.delete(opt_out)
            
        session.commit()
        
    return RedirectResponse(url="/admin/members?status=all", status_code=303)

@router.post("/campaign/preview", response_class=HTMLResponse)
async def preview_campaign(request: Request, plan_id: int = Form(...), session: Session = Depends(get_session)):
    login_required(request)
    
    plan = session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
        
    # Select eligible members (not opted out)
    # Note: We might want to re-send to pending people, or only new ones. 
    # For now, let's target anyone NOT opted out and NOT opted in (Pending)
    members = session.exec(
        select(Eligibility)
        .where(Eligibility.plan_id == plan_id)
        .where(Eligibility.opted_in == False)
        .where(Eligibility.opted_out == False)
    ).all()
    
    msg_preview = "Hi, this is Totl, working with your employer’s health plan. We help you get many labs and imaging tests at $0. When your doctor gives you an order, text us a photo and we’ll show you the nearest $0 options. Reply YES to enroll or NO to opt out."
    
    return templates.TemplateResponse("campaign_preview.html", {
        "request": request,
        "plan": plan,
        "members": members,
        "message_preview": msg_preview
    })

@router.post("/trigger_onboarding")
async def trigger_onboarding(
    request: Request, 
    plan_id: int = Form(...), 
    selected_members: list[int] = Form(...), 
    session: Session = Depends(get_session)
):
    login_required(request)
    from app.services.twilio_service import TwilioService
    twilio = TwilioService()
    
    # Fetch only the selected members
    members = session.exec(
        select(Eligibility)
        .where(Eligibility.id.in_(selected_members))
    ).all()
    
    sent_count = 0
    errors = []
    for m in members:
        msg = "Hi, this is Totl, working with your employer’s health plan. We help you get many labs and imaging tests at $0. When your doctor gives you an order, text us a photo and we’ll show you the nearest $0 options. Reply YES to enroll or NO to opt out."
        sid = twilio.send_sms(m.phone_number, msg, session=session)
        if sid:
            sent_count += 1
            # Log interaction
            session.add(MemberInteraction(
                member_id=m.id,
                message_type="outbound_campaign",
                content=msg
            ))
        else:
            errors.append(f"Failed to send to {m.phone_number}")
    
    session.commit()
        
    return templates.TemplateResponse("campaign_result.html", {
        "request": request,
        "sent_count": sent_count,
        "errors": errors
    })

@router.get("/members/{member_id}", response_class=HTMLResponse)
async def member_detail(request: Request, member_id: int, session: Session = Depends(get_session)):
    login_required(request)
    
    member = session.get(Eligibility, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    plans = session.exec(select(Plan)).all()
    
    # Fetch interactions
    interactions = session.exec(
        select(MemberInteraction)
        .where(MemberInteraction.member_id == member_id)
        .order_by(MemberInteraction.timestamp.asc())
    ).all()
    
    accumulator = session.exec(select(Accumulator).where(Accumulator.member_id == member_id).order_by(Accumulator.timestamp.desc())).first()
    
    return templates.TemplateResponse("member_detail.html", {
        "request": request,
        "member": member,
        "plans": plans,
        "interactions": interactions,
        "accumulator": accumulator
    })

@router.post("/members/{member_id}")
async def update_member(
    request: Request, 
    member_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone_number: str = Form(...),
    date_of_birth: str = Form(...),
    plan_id: int = Form(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    
    member = session.get(Eligibility, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    member.first_name = first_name
    member.last_name = last_name
    from app.core.utils import normalize_phone_number
    member.phone_number = normalize_phone_number(phone_number)
    member.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
    member.plan_id = plan_id
    
    session.add(member)
    session.commit()
    
    return RedirectResponse(url=f"/admin/members/{member_id}", status_code=303)

    return RedirectResponse(url=f"/admin/members/{member_id}", status_code=303)

@router.post("/members/{member_id}/send_message")
async def send_message(
    request: Request,
    member_id: int,
    message: str = Form(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    from app.services.twilio_service import TwilioService
    from app.db.models import Eligibility, MemberInteraction
    
    member = session.get(Eligibility, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    # Send SMS via Twilio Service
    twilio = TwilioService()
    # Note: send_sms handles logging if sid is returned, but we might want to force log here 
    # if send_sms fails or returns None (e.g. opt out).
    # Actually, send_sms returns SID if sent.
    
    sid = twilio.send_sms(member.phone_number, message, session=session)
    
    if sid:
        # Log interaction (outbound)
        # TwilioService doesn't log outbound automatically? 
        # Wait, in trigger_event we logged it manually.
        # In twilio_webhook we logged it manually.
        # So we should log it here.
        session.add(MemberInteraction(
            member_id=member.id,
            message_type="outbound_sms",
            content=message
        ))
        session.commit()
    else:
        # Failed or Opted Out
        # We should probably notify the admin, but for now just redirect.
        pass
        
    return RedirectResponse(url=f"/admin/members/{member_id}", status_code=303)

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, session: Session = Depends(get_session)):
    login_required(request)
    return templates.TemplateResponse("settings.html", {"request": request})


@router.post("/demo/trigger_event")
async def trigger_demo_event(
    request: Request,
    member_id: str = Form(...),
    cpt_code: str = Form(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    from app.services.tpa_ingestion import TPAIngestionService
    from app.db.models import Eligibility
    
    # Find the member by member_id string (e.g., "MEM001")
    member = session.exec(select(Eligibility).where(Eligibility.member_id == member_id)).first()
    
    if not member:
        return RedirectResponse(url=f"/admin/demo/console", status_code=303)
    
    # Simulate TPA Referral
    service = TPAIngestionService(session)
    
    # Ingest referral
    result = service.ingest_referrals([{
        "member_id": member_id,
        "cpt_code": cpt_code,
        "provider_npi": "1111111111"  # General Hospital (High Cost)
    }])
    
    if result["errors"]:
        print(f"DEBUG ADMIN: Ingestion Errors: {result['errors']}", flush=True)
    else:
        print(f"DEBUG ADMIN: Ingestion Success: {result['processed']} processed", flush=True)
    
    # Redirect back to demo console with the member selected
    return RedirectResponse(url=f"/admin/demo/console?member_id={member.id}", status_code=303)

@router.get("/demo/console", response_class=HTMLResponse)
async def demo_console(request: Request, member_id: int = None, session: Session = Depends(get_session)):
    login_required(request)
    from app.db.models import Eligibility, MemberInteraction
    
    # Get demo users
    demo_users = session.exec(select(Eligibility).where(Eligibility.member_id.in_(["MEM001", "MEM002"]))).all()
    
    selected_member = None
    interactions = []
    
    if member_id:
        selected_member = session.get(Eligibility, member_id)
        if selected_member:
            interactions = session.exec(
                select(MemberInteraction)
                .where(MemberInteraction.member_id == member_id)
                .order_by(MemberInteraction.timestamp.asc())
            ).all()
            
    return templates.TemplateResponse("demo_console.html", {
        "request": request,
        "demo_users": demo_users,
        "selected_member": selected_member,
        "interactions": interactions
    })

@router.post("/demo/simulate_inbound")
async def simulate_inbound(
    request: Request,
    member_id: int = Form(...),
    body: str = Form(None),
    action: str = Form(...), # 'text' or 'pic'
    session: Session = Depends(get_session)
):
    login_required(request)
    from app.db.models import Eligibility, MemberInteraction
    from app.services.twilio_service import TwilioService
    
    member = session.get(Eligibility, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    twilio = TwilioService()
    
    # Call the webhook logic directly instead of making HTTP requests
        
    if action == 'text':
        # Import the webhook function
        from app.routes.twilio import twilio_webhook
        
        # Call the webhook directly with the member's phone number and message
        try:
            response = await twilio_webhook(
                request=request,
                From=member.phone_number,
                Body=body if body else "",
                NumMedia=0,
                session=session
            )
            print(f"DEBUG ADMIN: Webhook returned: {response}", flush=True)
            
            # Log the simulated interaction (inbound)
            # REMOVED: Webhook already logs this
            # session.add(MemberInteraction(
            #     member_id=member.id,
            #     message_type="inbound_text",
            #     content=body if body else ""
            # ))
            
            # Parse response and log outbound interaction
            # The webhook returns TwiML, we'll extract the message
            if response and "<Message>" in str(response):
                import re
                match = re.search(r'<Message>(.*?)</Message>', str(response), re.DOTALL)
                if match:
                    outbound_msg = match.group(1).strip()
                    # RESTORED: Webhook returns TwiML but does NOT log the response. We must log it here for simulation.
                    session.add(MemberInteraction(
                        member_id=member.id,
                        message_type="outbound_sms",
                        content=outbound_msg
                    ))
            
            session.commit()
            print("DEBUG ADMIN: Session committed", flush=True)
        except Exception as e:
            print(f"DEBUG ADMIN: Simulation failed: {e}", flush=True)
            import traceback
            traceback.print_exc()
            
    elif action == 'pic':
        from app.routes.twilio import twilio_webhook
        from app.services.referral_image_service import ReferralImageService
        
        # Generate a realistic LabCorp referral image
        referral_service = ReferralImageService()
        try:
            image_url = referral_service.generate_general_hospital_referral(
                member_name=f"{member.first_name} {member.last_name}",
                provider_name="Dr. Jane Doe",
                test_name="MRI Knee"
            )
            full_url = f"http://localhost:8000{image_url}"
        except Exception as e:
            print(f"Failed to generate LabCorp referral: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to a simple placeholder
            full_url = "http://localhost:8000/static/placeholder.png"
        
        # Call the webhook with the generated image
        try:
            response = await twilio_webhook(
                request=request,
                From=member.phone_number,
                Body="",
                NumMedia=1,
                MediaUrl0=full_url,
                session=session
            )
            
            # Log interactions - REMOVED to prevent double logging (webhook handles it)
            # session.add(MemberInteraction(
            #     member_id=member.id,
            #     message_type="inbound_media",
            #     content=f"[Simulated LabCorp referral photo]"
            # ))
            
            # Parse response
            if response and "<Message>" in str(response):
                import re
                match = re.search(r'<Message>(.*?)</Message>', str(response), re.DOTALL)
                if match:
                    outbound_msg = match.group(1).strip()
                    session.add(MemberInteraction(
                        member_id=member.id,
                        message_type="outbound_sms",
                        content=outbound_msg
                    ))
            
            session.commit()
        except Exception as e:
            print(f"Simulation failed: {e}")
            import traceback
            traceback.print_exc()

    return RedirectResponse(url=f"/admin/demo/console?member_id={member_id}", status_code=303)


@router.post("/demo/reset")
async def reset_demo(
    request: Request,
    member_id: int = Form(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    from app.db.models import MemberInteraction, ReferralEvent, SupportMessage, Eligibility, OptOut
    from sqlmodel import delete, select, func
    
    print(f"DEBUG RESET: Hard Resetting member {member_id}", flush=True)
    
    try:
        # Count before
        count_interactions = session.exec(select(func.count()).select_from(MemberInteraction).where(MemberInteraction.member_id == member_id)).one()
        print(f"DEBUG RESET: Interactions before: {count_interactions}", flush=True)
        
        # 1. Delete interactions
        session.exec(delete(MemberInteraction).where(MemberInteraction.member_id == member_id))
        session.flush()
        
        # Verify interactions deleted
        count_after = session.exec(select(func.count()).select_from(MemberInteraction).where(MemberInteraction.member_id == member_id)).one()
        print(f"DEBUG RESET: Interactions after: {count_after}", flush=True)
        
        # 2. Delete referrals
        session.exec(delete(ReferralEvent).where(ReferralEvent.member_id == member_id))
        session.flush()
        
        # 3. Delete support messages
        session.exec(delete(SupportMessage).where(SupportMessage.member_id == member_id))
        session.flush()
        
        # 4. Reset Member Status
        member = session.get(Eligibility, member_id)
        if member:
            print(f"DEBUG RESET: Resetting eligibility for {member.first_name}", flush=True)
            # Check by member_id string (MEM001=Sean, MEM002=Jane)
            if member.member_id in ["MEM001", "MEM002"]: 
                member.opted_in = True
                member.opted_out = False
                # Ensure phone is normalized
                from app.core.utils import normalize_phone_number
                member.phone_number = normalize_phone_number(member.phone_number)
            else: # Bob (MEM003) or others
                member.opted_in = False
                member.opted_out = True
            session.add(member)
            
            # 5. Delete OptOut record
            from app.core.utils import normalize_phone_number
            normalized_number = normalize_phone_number(member.phone_number)
            session.exec(delete(OptOut).where(OptOut.phone_number == normalized_number))
            # Also try deleting raw just in case
            if normalized_number != member.phone_number:
                 session.exec(delete(OptOut).where(OptOut.phone_number == member.phone_number))
        
        session.commit()
        session.expire_all() # Force reload of all objects
        print(f"DEBUG RESET: Commit successful", flush=True)
        
    except Exception as e:
        print(f"DEBUG RESET: Error during reset: {e}", flush=True)
        session.rollback()
        import traceback
        traceback.print_exc()
        
    import time
    return RedirectResponse(url=f"/admin/demo/console?member_id={member_id}&t={int(time.time())}", status_code=303)
    
    return RedirectResponse(url=f"/admin/demo/console?member_id={member_id}", status_code=303)


# --- Integrations / TPA Data Management ---
@router.get("/integrations", response_class=HTMLResponse)
async def integrations_page(request: Request, session: Session = Depends(get_session)):
    login_required(request)
    return templates.TemplateResponse("integrations.html", {"request": request})

@router.post("/integrations/upload/eligibility", response_class=HTMLResponse)
async def upload_eligibility(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    try:
        from app.services.tpa_ingestion import TPAIngestionService
        import json
        
        content = await file.read()
        
        # Try JSON first
        try:
            data = json.loads(content.decode())
        except:
            # Try CSV
            import io
            csv_reader = csv.DictReader(io.StringIO(content.decode()))
            data = list(csv_reader)
        
        service = TPAIngestionService(session)
        result = service.ingest_eligibility(data)
        
        return templates.TemplateResponse("integrations.html", {
            "request": request,
            "message": f"Processed {result['processed']} eligibility records. Errors: {len(result['errors'])}"
        })
    except Exception as e:
        return templates.TemplateResponse("integrations.html", {
            "request": request,
            "error": str(e)
        })

@router.post("/integrations/upload/accumulators", response_class=HTMLResponse)
async def upload_accumulators(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    try:
        from app.services.tpa_ingestion import TPAIngestionService
        import json
        
        content = await file.read()
        try:
            data = json.loads(content.decode())
        except:
            import io
            csv_reader = csv.DictReader(io.StringIO(content.decode()))
            data = list(csv_reader)
        
        service = TPAIngestionService(session)
        result = service.ingest_accumulators(data)
        
        return templates.TemplateResponse("integrations.html", {
            "request": request,
            "message": f"Processed {result['processed']} accumulator records."
        })
    except Exception as e:
        return templates.TemplateResponse("integrations.html", {
            "request": request,
            "error": str(e)
        })

@router.post("/integrations/upload/claims", response_class=HTMLResponse)
async def upload_claims(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    try:
        from app.services.tpa_ingestion import TPAIngestionService
        import json
        
        content = await file.read()
        try:
            data = json.loads(content.decode())
        except:
            import io
            csv_reader = csv.DictReader(io.StringIO(content.decode()))
            data = list(csv_reader)
        
        service = TPAIngestionService(session)
        result = service.ingest_claims(data)
        
        return templates.TemplateResponse("integrations.html", {
            "request": request,
            "message": f"Processed {result['processed']} claims records."
        })
    except Exception as e:
        return templates.TemplateResponse("integrations.html", {
            "request": request,
            "error": str(e)
        })

@router.post("/integrations/upload/referrals", response_class=HTMLResponse)
async def upload_referrals(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    try:
        from app.services.tpa_ingestion import TPAIngestionService
        import json
        
        content = await file.read()
        try:
            data = json.loads(content.decode())
        except:
            import io
            csv_reader = csv.DictReader(io.StringIO(content.decode()))
            data = list(csv_reader)
        
        # Call TPA ingestion
        service = TPAIngestionService(session)
        result = service.ingest_referrals(data)
        if result["errors"]:
            print(f"DEBUG ADMIN: Ingestion Errors: {result['errors']}", flush=True)
        else:
            print(f"DEBUG ADMIN: Ingestion Success: {result['processed']} processed", flush=True)
        
        return templates.TemplateResponse("integrations.html", {
            "request": request,
            "message": f"Processed {result['processed']} referral records."
        })
    except Exception as e:
        return templates.TemplateResponse("integrations.html", {
            "request": request,
            "error": str(e)
        })

# Sample file download endpoints
from fastapi.responses import StreamingResponse
import io

@router.get("/integrations/sample/eligibility")
async def sample_eligibility(request: Request):
    login_required(request)
    csv_data = """member_id,first_name,last_name,date_of_birth,phone_number,zip_code,plan_id,risk_tier
MEM001,John,Doe,1985-01-15,+15551234567,18015,1,Low
MEM002,Jane,Smith,1990-06-20,+15559876543,18018,1,Medium
"""
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=eligibility_sample.csv"}
    )

@router.get("/integrations/sample/accumulators")
async def sample_accumulators(request: Request):
    login_required(request)
    csv_data = """member_id,deductible_met,oop_met,deductible_limit,oop_limit
MEM001,500.00,600.00,3000.00,6000.00
MEM002,3000.00,3500.00,3000.00,6000.00
"""
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=accumulators_sample.csv"}
    )

@router.get("/integrations/sample/claims")
async def sample_claims(request: Request):
    login_required(request)
    csv_data = """member_id,date_of_service,cpt_code,diagnosis_code,allowed_amount,provider_npi
MEM001,2024-01-15,99214,I10,150.00,1234567890
MEM001,2024-02-20,80053,E11,75.00,1234567890
"""
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=claims_sample.csv"}
    )

@router.get("/integrations/sample/referrals")
async def sample_referrals(request: Request):
    login_required(request)
    csv_data = """member_id,cpt_code,provider_npi
MEM001,80050,9999999999
MEM002,73721,9999999999
"""
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=referrals_sample.csv"}
    )

# --- Support Queue ---
@router.get("/support", response_class=HTMLResponse)
async def support_queue(request: Request, filter: str = "active", session: Session = Depends(get_session)):
    login_required(request)
    from app.db.models import SupportMessage
    
    query = select(SupportMessage)
    
    if filter == "resolved":
        query = query.where(SupportMessage.status == "resolved")
    else:
        query = query.where(SupportMessage.status.in_(["pending", "replied"]))
        
    messages = session.exec(
        query.order_by(SupportMessage.timestamp.desc())
    ).all()
    
    return templates.TemplateResponse("support.html", {
        "request": request,
        "messages": messages,
        "current_filter": filter
    })

@router.post("/support/{message_id}/reply", response_class=HTMLResponse)
async def support_reply(
    request: Request,
    message_id: int,
    reply: str = Form(...),
    session: Session = Depends(get_session)
):
    login_required(request)
    from app.db.models import SupportMessage
    from app.services.twilio_service import TwilioService
    
    support_msg = session.get(SupportMessage, message_id)
    if not support_msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Send SMS reply
    twilio = TwilioService()
    twilio.send_sms(support_msg.member.phone_number, reply)
    
    # Update support message
    support_msg.admin_reply = reply
    support_msg.status = "replied"
    session.add(support_msg)
    session.commit()
    
    # Redirect back to support queue
    return RedirectResponse(url="/admin/support", status_code=303)

@router.post("/support/{message_id}/resolve", response_class=HTMLResponse)
async def support_resolve(
    request: Request,
    message_id: int,
    session: Session = Depends(get_session)
):
    login_required(request)
    from app.db.models import SupportMessage
    from datetime import datetime
    
    support_msg = session.get(SupportMessage, message_id)
    if not support_msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    support_msg.status = "resolved"
    support_msg.resolved_at = datetime.utcnow()
    session.add(support_msg)
    session.commit()
    
    return RedirectResponse(url="/admin/support", status_code=303)
print('ADMIN MODULE LOADED', flush=True)

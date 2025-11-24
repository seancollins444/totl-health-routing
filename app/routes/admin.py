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

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
settings = get_settings()

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
                    phone_number=row["phone_number"],
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
        sid = twilio.send_sms(m.phone_number, msg)
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
    member.phone_number = phone_number
    member.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
    member.plan_id = plan_id
    
    session.add(member)
    session.commit()
    
    return RedirectResponse(url=f"/admin/members/{member_id}", status_code=303)

    return RedirectResponse(url=f"/admin/members/{member_id}", status_code=303)

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, session: Session = Depends(get_session)):
    login_required(request)
    return templates.TemplateResponse("settings.html", {"request": request})

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
            
            # Log the simulated interaction (inbound)
            session.add(MemberInteraction(
                member_id=member.id,
                message_type="inbound_text",
                content=body if body else ""
            ))
            
            # Parse response and log outbound interaction
            # The webhook returns TwiML, we'll extract the message
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
            
    elif action == 'pic':
        from app.routes.twilio import twilio_webhook
        from starlette.datastructures import FormData
        
        # For picture simulation, we need to provide media URL
        # We'll just log it and create a fake interaction
        try:
            response = await twilio_webhook(
                request=request,
                From=member.phone_number,
                Body="",
                NumMedia=1,
                session=session
            )
            
            # Log interactions
            session.add(MemberInteraction(
                member_id=member.id,
                message_type="inbound_media",
                content="[Simulated referral photo]"
            ))
            
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
    from app.db.models import MemberInteraction
    
    # Delete all interactions for this member
    interactions = session.exec(
        select(MemberInteraction).where(MemberInteraction.member_id == member_id)
    ).all()
    
    for interaction in interactions:
        session.delete(interaction)
    
    session.commit()
    
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
        
        service = TPAIngestionService(session)
        result = service.ingest_referrals(data)
        
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
async def support_queue(request: Request, session: Session = Depends(get_session)):
    login_required(request)
    from app.db.models import SupportMessage
    
    # Get all pending and replied messages
    messages = session.exec(
        select(SupportMessage)
        .where(SupportMessage.status.in_(["pending", "replied"]))
        .order_by(SupportMessage.timestamp.desc())
    ).all()
    
    return templates.TemplateResponse("support.html", {
        "request": request,
        "messages": messages
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

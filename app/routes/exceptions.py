import csv
from io import StringIO
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from app.db.models import CPTNPIException, Plan, Employer
from app.db.session import get_session
from fastapi import APIRouter, Depends, Request

router = APIRouter()

@router.get("/admin/exceptions/export")
async def export_exceptions(
    request: Request,
    plan_id: int = None,
    session: Session = Depends(get_session)
):
    """Export CPT-NPI exception list as CSV for TPA submission"""
    from app.routes.admin import login_required
    login_required(request)
    
    # Get exceptions
    query = select(CPTNPIException).where(CPTNPIException.is_active == True)
    if plan_id:
        query = query.where(CPTNPIException.plan_id == plan_id)
    
    exceptions = session.exec(query).all()
    
    # Build CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'group_id',
        'plan_id', 
        'cpt_bundle_id',
        'cpt_list',
        'npi',
        'cost_share_type',
        'member_cost_share',
        'avg_savings',
        'p10_savings',
        'episode_count'
    ])
    
    # Rows
    # Rows
    if not exceptions:
        # Write sample row if no data
        writer.writerow([
            'GRP12345', '1', 'BUN001', '73721,73722', '1234567890', 
            'copay', '50.00', '200.00', '150.00', '10'
        ])
    else:
        for exc in exceptions:
            plan = session.get(Plan, exc.plan_id)
            employer = session.get(Employer, plan.employer_id) if plan else None
            
            writer.writerow([
                employer.id if employer else '',
                exc.plan_id,
                exc.cpt_bundle_id,
                exc.cpt_list,
                exc.npi,
                exc.cost_share_type,
                f"{exc.member_cost_share:.2f}",
                f"{exc.avg_savings:.2f}",
                f"{exc.p10_savings:.2f}",
                exc.episode_count
            ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tpa_exception_list.csv"}
    )

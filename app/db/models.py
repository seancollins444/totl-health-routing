from typing import Optional, List
from datetime import datetime, date
from sqlmodel import SQLModel, Field, Relationship, JSON
from sqlalchemy import Column, String, Boolean, Integer, Float, Date, DateTime, ForeignKey, Text

# --- Users (Admin) ---
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    hashed_password: str

# --- Core Entities ---
class Employer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    notes: Optional[str] = None
    
    plans: List["Plan"] = Relationship(back_populates="employer")

class Plan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    employer_id: int = Field(foreign_key="employer.id")
    tpa_name: Optional[str] = None
    
    employer: Employer = Relationship(back_populates="plans")
    members: List["Eligibility"] = Relationship(back_populates="plan")
    rules: List["CPTApprovalRule"] = Relationship(back_populates="plan")

class Eligibility(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    member_id: str = Field(index=True) # Unique ID from employer
    first_name: str
    last_name: str
    date_of_birth: date
    phone_number: str = Field(index=True) # Normalized E.164
    zip_code: Optional[str] = Field(default=None) # For geo-routing
    plan_id: int = Field(foreign_key="plan.id")
    
    opted_in: bool = False
    opted_out: bool = False # No-contact list
    opted_in_date: Optional[date] = None  # Date they opted in
    total_savings: float = Field(default=0.0)  # Cumulative savings
    
    # New Risk Tier
    risk_tier: str = Field(default="Low") # Low, Medium, High
    
    plan: Plan = Relationship(back_populates="members")
    interactions: List["MemberInteraction"] = Relationship(back_populates="member")
    accumulators: List["Accumulator"] = Relationship(back_populates="member")
    referrals: List["ReferralEvent"] = Relationship(back_populates="member")
    claims: List["Claim"] = Relationship(back_populates="member")

class Facility(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    npi: str = Field(unique=True, index=True)
    facility_name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class EOB(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    member_id_ref: str # Reference to member_id, might not link directly if member not in eligibility yet
    plan_id: int = Field(foreign_key="plan.id")
    date_of_service: date
    cpt_code: str = Field(index=True)
    npi: str = Field(index=True)
    allowed_amount: float
    place_of_service: Optional[str] = None
    facility_name: Optional[str] = None

class CPTApprovalRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="plan.id")
    cpt_code: str
    requires_approval: bool = True
    auto_approve_threshold: Optional[float] = None
    
    plan: Plan = Relationship(back_populates="rules")

class CPTNPIException(SQLModel, table=True):
    """Pre-approved CPT-NPI combinations for TPA exception files"""
    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="plan.id")
    cpt_bundle_id: str  # Hash/ID for CPT set (e.g., "LAB_SET_A")
    cpt_list: str  # Comma-separated CPT codes (e.g., "80050,80053,84443")
    npi: str  # Facility NPI
    cost_share_type: str = "override"  # override, waive, etc.
    member_cost_share: float = 0.0  # Target cost share (usually 0)
    avg_savings: float  # Average net savings per episode
    p10_savings: float  # 10th percentile (worst-case) savings
    episode_count: int = 0  # Number of episodes in calculation
    is_active: bool = True

class MemberInteraction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    member_id: int = Field(foreign_key="eligibility.id")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_type: str # inbound_text, inbound_media, outbound_text, outbound_campaign
    inbound_type: Optional[str] = None # Deprecated/Optional
    inbound_content_summary: Optional[str] = None
    content: Optional[str] = None # Actual message content
    cpt_codes_extracted: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    routing_result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    had_match: bool = False
    
    member: Eligibility = Relationship(back_populates="interactions")

class OptOut(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    phone_number: str = Field(unique=True, index=True)
    reason: str # STOP, NO
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# --- New TPA Models ---

class Accumulator(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    member_id: int = Field(foreign_key="eligibility.id")
    deductible_met: float = 0.0
    oop_met: float = 0.0
    deductible_limit: float = 3000.0 # Default/Simulated
    oop_limit: float = 6000.0 # Default/Simulated
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    member: Eligibility = Relationship(back_populates="accumulators")

class ReferralEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    member_id: int = Field(foreign_key="eligibility.id")
    cpt_code: str
    service_name: Optional[str] = None
    ordering_provider_npi: Optional[str] = None
    
    # Baseline (what would have happened without Totl)
    baseline_npi: Optional[str] = None  # Default hospital/facility member would have used
    baseline_allowed: Optional[float] = None  # Total allowed at baseline for CPT bundle
    
    # Redirected (what actually happened)
    redirected_npi: Optional[str] = None  # Facility Totl sent them to
    redirected_allowed: Optional[float] = None  # Total allowed at redirected facility
    
    # Savings calculation (plan-level, adjusted for member cost-share)
    member_cost_share: float = 0.0  # What member paid (usually 0 if waived)
    plan_cost_baseline: Optional[float] = None  # What plan would have paid
    plan_cost_redirected: Optional[float] = None  # What plan actually paid
    net_savings: Optional[float] = None  # plan_cost_baseline - plan_cost_redirected
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "received" # received, processed, engaged, suppressed
    
    member: Eligibility = Relationship(back_populates="referrals")

class Claim(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    member_id: int = Field(foreign_key="eligibility.id")
    date_of_service: date
    cpt_code: str
    diagnosis_code: Optional[str] = None
    allowed_amount: float
    provider_npi: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    member: Eligibility = Relationship(back_populates="claims")

class SupportMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    member_id: int = Field(foreign_key="eligibility.id")
    message_content: str
    media_url: Optional[str] = None  # For referral photos
    status: str = "pending"  # pending, replied, resolved
    admin_reply: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    
    member: Eligibility = Relationship()

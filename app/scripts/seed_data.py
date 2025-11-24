from sqlmodel import Session, select
from app.db.models import User, Employer, Plan, Eligibility, Accumulator, Claim, Facility, CPTApprovalRule, CPTNPIException, EOB
from app.db.session import engine
from datetime import date, datetime, timedelta
import random

def seed_data():
    with Session(engine) as session:
        print("Seeding data...")
        
        # 1. Create Employers & Plans
        # Employer 1: Acme Corp
        acme = session.exec(select(Employer).where(Employer.name == "Acme Corp")).first()
        if not acme:
            acme = Employer(name="Acme Corp", notes="Manufacturing company")
            session.add(acme)
            session.commit()
            session.refresh(acme)
            
        acme_plan = session.exec(select(Plan).where(Plan.name == "Acme PPO Gold")).first()
        if not acme_plan:
            acme_plan = Plan(name="Acme PPO Gold", employer_id=acme.id, tpa_name="HealthFlow TPA")
            session.add(acme_plan)
            session.commit()
            session.refresh(acme_plan)

        # Employer 2: TechStart Inc
        techstart = session.exec(select(Employer).where(Employer.name == "TechStart Inc")).first()
        if not techstart:
            techstart = Employer(name="TechStart Inc", notes="Technology startup")
            session.add(techstart)
            session.commit()
            session.refresh(techstart)
            
        techstart_plan = session.exec(select(Plan).where(Plan.name == "TechStart HDHP")).first()
        if not techstart_plan:
            techstart_plan = Plan(name="TechStart HDHP", employer_id=techstart.id, tpa_name="HealthFlow TPA")
            session.add(techstart_plan)
            session.commit()
            session.refresh(techstart_plan)

        # 2. Create Members
        # Member 1: Sean Collins (Acme Corp) - High Risk, Deductible Met
        sean = session.exec(select(Eligibility).where(Eligibility.phone_number == "6104171957")).first()
        if not sean:
            sean = Eligibility(
                member_id="MEM001",
                first_name="Sean",
                last_name="Collins",
                date_of_birth=date(1985, 5, 15),
                phone_number="6104171957",
                zip_code="18015",  # Bethlehem, PA
                plan_id=acme_plan.id,
                risk_tier="High",
                opted_in=True,
                opted_in_date=date.today(),
                total_savings=450.00  # Demo savings from previous referrals
            )
            session.add(sean)
            session.commit()
            session.refresh(sean)
            
            # Accumulator for Sean - Deductible MET for $0 viability
            session.add(Accumulator(
                member_id=sean.id,
                deductible_met=3000.0,  # Fully met
                oop_met=3000.0,
                deductible_limit=3000.0,
                oop_limit=6000.0
            ))
            
            # Claims for Sean (High Risk History)
            # CPT 80050 - Expensive labs, NOT viable for $0 OOP (price >= $100)
            session.add(Claim(
                member_id=sean.id,
                date_of_service=date(2025, 1, 15),
                cpt_code="80050",
                provider_npi="1234567890",
                allowed_amount=300.0  # Over $100 threshold, coinsurance applies
            ))
            # CPT 73721 - Discounted MRI, viable for $0 OOP
            session.add(Claim(
                member_id=sean.id,
                date_of_service=date(2024, 11, 10),
                cpt_code="73721",
                provider_npi="1234567890",
                allowed_amount=85.0  # Under $100, viable for $0 OOP
            ))

        # Member 2: Jane Doe (TechStart Inc) - Low Risk, Deductible Met
        jane = session.exec(select(Eligibility).where(Eligibility.member_id == "MEM002")).first()
        if not jane:
            jane = Eligibility(
                member_id="MEM002",
                first_name="Jane",
                last_name="Doe",
                date_of_birth=date(1990, 3, 20),
                phone_number="5551234567",
                zip_code="18018",  # Bethlehem, PA (nearby)
                plan_id=techstart_plan.id,
                risk_tier="Low",
                opted_in=True,
                opted_in_date=date.today(),
                total_savings=125.00  # Demo savings
            )
            session.add(jane)
            session.commit()
            session.refresh(jane)
            
            # Accumulator for Jane (Met Deductible)
            session.add(Accumulator(
                member_id=jane.id,
                deductible_met=3000.0,
                oop_met=3500.0,
                deductible_limit=3000.0,
                oop_limit=6000.0
            ))

        # Member 3: Bob Smith (Acme Corp) - Low Risk, High Deductible Remaining
        bob = session.exec(select(Eligibility).where(Eligibility.member_id == "MEM003")).first()
        if not bob:
            bob = Eligibility(
                member_id="MEM003",
                first_name="Bob",
                last_name="Smith",
                date_of_birth=date(1978, 11, 5),
                phone_number="5559876543",
                zip_code="19001",  # Philadelphia area (farther away)
                plan_id=acme_plan.id,
                risk_tier="Low",
                opted_in=False,
                total_savings=0.00
            )
            session.add(bob)
            session.commit()
            session.refresh(bob)
            
            # Accumulator for Bob (Low Met)
            session.add(Accumulator(
                member_id=bob.id,
                deductible_met=100.0,
                oop_met=100.0,
                deductible_limit=3000.0,
                oop_limit=6000.0
            ))

        # Facilities
        fac1 = session.exec(select(Facility).where(Facility.npi == "1111111111")).first()
        if not fac1:
            fac1 = Facility(
                npi="1111111111",
                facility_name="General Hospital Imaging",
                facility_type="Hospital",
                address="123 Main St",
                city="Bethlehem",
                state="PA",
                zip_code="18015"  # Close to Sean
            )
            session.add(fac1)
            
        fac2 = session.exec(select(Facility).where(Facility.npi == "2222222222")).first()
        if not fac2:
            fac2 = Facility(
                npi="2222222222",
                facility_name="QuickLab Freestanding Center",
                facility_type="Freestanding",
                address="456 Elm Ave",
                city="Allentown",
                state="PA",
                zip_code="18103"  # ~10 miles from Sean
            )
            session.add(fac2)
            
        fac3 = session.exec(select(Facility).where(Facility.npi == "3333333333")).first()
        if not fac3:
            fac3 = Facility(
                npi="3333333333",
                facility_name="LabCorp Express",
                facility_type="Freestanding",
                address="789 Oak Blvd",
                city="Easton",
                state="PA",
                zip_code="18042"  # ~8 miles from Sean
            )
            session.add(fac3)
        
        # CPT-NPI Exceptions (Pre-approved combinations for TPA)
        exc1 = session.exec(select(CPTNPIException).where(
            CPTNPIException.cpt_bundle_id == "MRI_KNEE_WO"
        )).first()
        if not exc1:
            session.add(CPTNPIException(
                plan_id=acme_plan.id,
                cpt_bundle_id="MRI_KNEE_WO",
                cpt_list="73721",
                npi="2222222222",  # QuickLab
                cost_share_type="override",
                member_cost_share=0.0,
                avg_savings=2050.0,
                p10_savings=1500.0,
                episode_count=25,
                is_active=True
            ))
        
        # Exception 2: Lab panel at LabCorp
        exc2 = session.exec(select(CPTNPIException).where(
            CPTNPIException.cpt_bundle_id == "BASIC_METABOLIC"
        )).first()
        if not exc2:
            session.add(CPTNPIException(
                plan_id=acme_plan.id,
                cpt_bundle_id="BASIC_METABOLIC",
                cpt_list="80050,84443,85025",
                npi="3333333333",  # LabCorp
                cost_share_type="override",
                member_cost_share=0.0,
                avg_savings=270.0,
                p10_savings=200.0,
                episode_count=150,
                is_active=True
            ))
            
        # 4. Create EOBs (Price Transparency Data) for PricingService
        # EOB 1: General Hospital - Expensive MRI
        eob1 = session.exec(select(EOB).where(EOB.npi == "1111111111", EOB.cpt_code == "73721")).first()
        if not eob1:
            session.add(EOB(
                member_id_ref="HISTORICAL",
                plan_id=acme_plan.id,
                date_of_service=date(2023, 1, 1),
                cpt_code="73721",
                npi="1111111111",
                allowed_amount=2500.00,
                facility_name="General Hospital Imaging"
            ))

        # EOB 2: QuickLab - Cheap MRI
        eob2 = session.exec(select(EOB).where(EOB.npi == "2222222222", EOB.cpt_code == "73721")).first()
        if not eob2:
            session.add(EOB(
                member_id_ref="HISTORICAL",
                plan_id=acme_plan.id,
                date_of_service=date(2023, 1, 1),
                cpt_code="73721",
                npi="2222222222",
                allowed_amount=450.00,
                facility_name="QuickLab Freestanding Center"
            ))
            
        # EOB 3: General Hospital - Expensive Labs (80050)
        eob3 = session.exec(select(EOB).where(EOB.npi == "1111111111", EOB.cpt_code == "80050")).first()
        if not eob3:
            session.add(EOB(
                member_id_ref="HISTORICAL",
                plan_id=acme_plan.id,
                date_of_service=date(2023, 1, 1),
                cpt_code="80050",
                npi="1111111111",
                allowed_amount=300.00,
                facility_name="General Hospital Labs"
            ))
            
        # EOB 4: LabCorp - Cheap Labs (80050)
        eob4 = session.exec(select(EOB).where(EOB.npi == "3333333333", EOB.cpt_code == "80050")).first()
        if not eob4:
            session.add(EOB(
                member_id_ref="HISTORICAL",
                plan_id=acme_plan.id,
                date_of_service=date(2023, 1, 1),
                cpt_code="80050",
                npi="3333333333",
                allowed_amount=30.00,
                facility_name="LabCorp Express"
            ))

        # 5. Create CPT Approval Rules (Required for PricingService to consider them)
        # Rule for MRI
        rule1 = session.exec(select(CPTApprovalRule).where(CPTApprovalRule.cpt_code == "73721")).first()
        if not rule1:
            session.add(CPTApprovalRule(plan_id=acme_plan.id, cpt_code="73721", requires_approval=True))
            
        # Rule for Labs
        rule2 = session.exec(select(CPTApprovalRule).where(CPTApprovalRule.cpt_code == "80050")).first()
        if not rule2:
            session.add(CPTApprovalRule(plan_id=acme_plan.id, cpt_code="80050", requires_approval=False))

        session.commit()
        print("Seeding complete.")

if __name__ == "__main__":
    seed_data()

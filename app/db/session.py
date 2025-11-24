from sqlmodel import create_engine, Session, SQLModel
from app.core.config import get_settings

settings = get_settings()

# Use connect_args={"check_same_thread": False} only for SQLite
connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)

def get_session():
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    
    # Seed default data
    with Session(engine) as session:
        from app.db.models import Employer, Plan
        from sqlmodel import select
        
        # Check for employer
        employer = session.exec(select(Employer).where(Employer.name == "Default Employer")).first()
        if not employer:
            employer = Employer(name="Default Employer")
            session.add(employer)
            session.commit()
            session.refresh(employer)
            
        # Check for plan
        plan = session.exec(select(Plan).where(Plan.id == 1)).first()
        if not plan:
            plan = Plan(name="Default Plan", employer_id=employer.id)
            session.add(plan)
            session.commit()

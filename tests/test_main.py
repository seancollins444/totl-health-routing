import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from app.main import app
from app.db.session import get_session
from app.db.models import Eligibility, Plan, Employer

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session
    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

def test_read_main(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Totl API is running"}

def test_admin_login_page(client: TestClient):
    response = client.get("/admin/login")
    assert response.status_code == 200
    assert "Login" in response.text

def test_eligibility_model(session: Session):
    emp = Employer(name="Test Corp")
    session.add(emp)
    session.commit()
    
    plan = Plan(name="PPO", employer_id=emp.id)
    session.add(plan)
    session.commit()
    
    member = Eligibility(
        member_id="M123",
        first_name="John",
        last_name="Doe",
        date_of_birth="1980-01-01",
        phone_number="+15551234567",
        plan_id=plan.id
    )
    session.add(member)
    session.commit()
    
    assert member.id is not None
    assert member.opted_in is False

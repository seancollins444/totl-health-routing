import sys
if sys.version_info < (3, 10):
    import importlib.metadata
    import importlib_metadata
    if not hasattr(importlib.metadata, "packages_distributions"):
        importlib.metadata.packages_distributions = importlib_metadata.packages_distributions

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from app.routes import twilio, admin, tpa, exceptions
from app.db.session import create_db_and_tables
from app.core.config import get_settings
from contextlib import asynccontextmanager

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(title="Totl", lifespan=lifespan)

# Add session middleware for admin auth
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(twilio.router, prefix="/twilio", tags=["Twilio"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(tpa.router, prefix="/tpa", tags=["TPA"])
app.include_router(exceptions.router)

@app.get("/")
def root():
    return {"message": "Totl API is running"}

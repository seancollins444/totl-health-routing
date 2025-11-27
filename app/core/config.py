import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    APP_ENV: str = "local"
    PROJECT_NAME: str = "Totl"
    
    # Database
    DATABASE_URL: str = "sqlite:///./totl.db"
    
    # Security
    SECRET_KEY: str
    
    # Twilio
    TWILIO_ACCOUNT_SID: str = "dummy_sid"
    TWILIO_AUTH_TOKEN: str = "dummy_token"
    TWILIO_PHONE_NUMBER: str = "+1234567890"
    
    # Google Gemini
    GOOGLE_API_KEY: str = "dummy_google_key"
    GOOGLE_MAPS_API_KEY: str = "dummy_maps_key"
    
    # App
    BASE_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="allow", case_sensitive=True)

@lru_cache()
def get_settings():
    return Settings()

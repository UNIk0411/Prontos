import os
from pathlib import Path

from pydantic import BaseModel, model_validator

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / 'data' / 'prontos.db'


class Settings(BaseModel):
    db_path: str = os.getenv('PRONTOS_DB_PATH', str(DB_PATH))
    jwt_secret: str = os.getenv('PRONTOS_JWT_SECRET', 'prontos-local-development-secret')
    api_cors_origins: list[str] = [
        origin.strip() for origin in os.getenv('PRONTOS_CORS_ORIGINS', '*').split(',') if origin.strip()
    ]
    environment: str = os.getenv('PRONTOS_ENV', 'development')
    bootstrap_admin_email: str = os.getenv('PRONTOS_BOOTSTRAP_ADMIN_EMAIL', '')
    bootstrap_admin_username: str = os.getenv('PRONTOS_BOOTSTRAP_ADMIN_USERNAME', '')
    bootstrap_admin_password: str = os.getenv('PRONTOS_BOOTSTRAP_ADMIN_PASSWORD', '')

    @model_validator(mode='after')
    def validate_production_secrets(self) -> 'Settings':
        if self.environment.lower() == 'production':
            if self.jwt_secret == 'prontos-local-development-secret' or len(self.jwt_secret) < 32:
                raise ValueError('PRONTOS_JWT_SECRET must be set to at least 32 characters in production')
            if not self.api_cors_origins or '*' in self.api_cors_origins:
                raise ValueError('PRONTOS_CORS_ORIGINS must explicitly list trusted origins in production')
        return self


settings = Settings()

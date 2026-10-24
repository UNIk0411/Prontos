import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User
from app.db.session import SessionLocal


ROLE_VALUES = {'viewer', 'operator', 'admin', 'platform_admin'}


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _b64url_decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f'pbkdf2_sha256${iterations}${_b64url_encode(salt)}${_b64url_encode(digest)}'


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith('pbkdf2_sha256$'):
        try:
            _, iterations, salt, expected = password_hash.split('$', 3)
            digest = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                _b64url_decode(salt),
                int(iterations),
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(_b64url_encode(digest), expected)

    legacy_digest = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        settings.jwt_secret.encode('utf-8'),
        100_000,
    ).hex()
    return hmac.compare_digest(legacy_digest, password_hash)


def seed_users(db: Session) -> None:
    if settings.environment.lower() == 'production':
        email = settings.bootstrap_admin_email.strip().lower()
        username = settings.bootstrap_admin_username.strip()
        if email:
            admin = db.query(User).filter(User.email == email).first()
            if admin is not None:
                if admin.role != 'platform_admin' or not admin.is_active:
                    raise RuntimeError(
                        'The configured bootstrap administrator already exists but is not an active platform administrator'
                    )
                return
            if not username or len(settings.bootstrap_admin_password) < 12:
                raise RuntimeError(
                    'Set PRONTOS_BOOTSTRAP_ADMIN_USERNAME and a 12-character '
                    'PRONTOS_BOOTSTRAP_ADMIN_PASSWORD to create the production administrator'
                )
            username_owner = db.query(User).filter(User.username == username).first()
            if username_owner is not None:
                raise RuntimeError('PRONTOS_BOOTSTRAP_ADMIN_USERNAME is already in use')
            db.add(User(
                id=f'user-{username}',
                organization_id='prontos-demo',
                email=email,
                username=username,
                password_hash=hash_password(settings.bootstrap_admin_password),
                role='platform_admin',
                is_active=True,
            ))
            db.commit()
            return
        if db.query(User).count() == 0:
            raise RuntimeError(
                'Set PRONTOS_BOOTSTRAP_ADMIN_EMAIL, PRONTOS_BOOTSTRAP_ADMIN_USERNAME, '
                'and a 12-character PRONTOS_BOOTSTRAP_ADMIN_PASSWORD before first production startup'
            )
        return

    if db.query(User).count() > 0:
        demo_admin = db.query(User).filter(User.email == 'admin@prontos.local').first()
        if demo_admin is not None and demo_admin.role == 'admin':
            demo_admin.role = 'platform_admin'
            db.commit()
        return

    defaults = [
        ('admin@prontos.local', 'admin', 'admin123', 'platform_admin'),
        ('operator@prontos.local', 'operator', 'operator123', 'operator'),
        ('viewer@prontos.local', 'viewer', 'viewer123', 'viewer'),
    ]

    for email, username, password, role in defaults:
        db.add(User(
            id=f'user-{username}',
            organization_id='prontos-demo',
            email=email,
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        ))
    db.commit()


def create_token(user: User) -> str:
    header = {'alg': 'HS256', 'typ': 'JWT'}
    payload = {
        'sub': user.email,
        'username': user.username,
        'role': user.role,
        'exp': int(time.time()) + 60 * 60 * 12,
    }
    signing_input = (
        f"{_b64url_encode(json.dumps(header, separators=(',', ':'), sort_keys=True).encode('utf-8'))}."
        f"{_b64url_encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8'))}"
    ).encode('utf-8')
    signature = hmac.new(settings.jwt_secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
    return f"{signing_input.decode('ascii')}.{_b64url_encode(signature)}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split('.')
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token') from exc

    signing_input = f'{header_b64}.{payload_b64}'.encode('ascii')
    expected = _b64url_encode(hmac.new(settings.jwt_secret.encode('utf-8'), signing_input, hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature_b64):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token signature')

    try:
        header = json.loads(_b64url_decode(header_b64).decode('utf-8'))
        payload = json.loads(_b64url_decode(payload_b64).decode('utf-8'))
        if header.get('alg') != 'HS256' or not isinstance(payload, dict):
            raise ValueError('Unsupported token format')
        expires_at = float(payload.get('exp', 0))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token payload') from exc
    if expires_at < time.time():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token expired')
    return payload


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.lower()).first()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid email or password')
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User is inactive')
    return user


def get_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Missing authorization header')
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authorization header must use Bearer token')

    payload = decode_token(token)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == payload.get('sub')).first()
    finally:
        db.close()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found or inactive')
    return {
        'email': user.email,
        'username': user.username,
        'role': user.role,
        'organization_id': user.organization_id,
    }


def require_roles(*roles: str):
    allowed = set(roles)

    def dependency(current_user: dict[str, str] = Depends(get_current_user)) -> dict[str, str]:
        if current_user.get('role') not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Insufficient role privileges')
        return current_user

    return dependency

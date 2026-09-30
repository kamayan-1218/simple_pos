import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import StaffUser, RefreshToken, utcnow

hasher = PasswordHasher()

def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def invalid_auth():
    raise HTTPException(401, detail={"code": "AUTH_INVALID", "message": "認証できません"})

def issue_tokens(db: Session, staff: StaffUser) -> dict:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_minutes)
    claims = {"sub": str(staff.id), "role": staff.role, "iat": now, "exp": expires,
              "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "jti": secrets.token_hex(16)}
    access = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    refresh = secrets.token_urlsafe(48)
    db.add(RefreshToken(staff_user_id=staff.id, token_hash=digest(refresh),
                        expires_at=utcnow() + timedelta(hours=settings.refresh_hours)))
    db.commit()
    return {"access_token": access, "refresh_token": refresh,
            "expires_at": expires.isoformat(),
            "staff": {"id": staff.id, "staff_code": staff.staff_code,
                      "display_name": staff.display_name}}

def rotate_refresh(db: Session, token: str) -> dict:
    record = db.query(RefreshToken).filter_by(token_hash=digest(token), revoked_at=None).first()
    if not record or record.expires_at <= utcnow():
        invalid_auth()
    staff = db.get(StaffUser, record.staff_user_id)
    if not staff or not staff.is_active:
        invalid_auth()
    record.revoked_at = utcnow()
    # Commit revocation before issuing a successor. A second use cannot rotate it.
    db.commit()
    return issue_tokens(db, staff)

def revoke_refresh(db: Session, token: str):
    record = db.query(RefreshToken).filter_by(token_hash=digest(token), revoked_at=None).first()
    if record:
        record.revoked_at = utcnow()
        db.commit()

def current_staff(authorization: str | None = Header(default=None),
                  db: Session = Depends(get_db)) -> StaffUser:
    if not authorization or not authorization.startswith("Bearer "):
        invalid_auth()
    try:
        claims = jwt.decode(authorization[7:], settings.jwt_secret,
                            algorithms=["HS256"], audience=settings.jwt_audience,
                            issuer=settings.jwt_issuer, options={"require": ["sub", "exp", "iat", "jti"]})
        staff = db.get(StaffUser, int(claims["sub"]))
    except (jwt.PyJWTError, ValueError, TypeError):
        invalid_auth()
    if not staff or not staff.is_active:
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "担当者は無効です"})
    if staff.role != "CASHIER":
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "POS操作の権限がありません"})
    return staff

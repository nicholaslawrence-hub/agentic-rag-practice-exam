"""Validate NextAuth JWTs and inject a User into FastAPI request dependencies."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.models import User
from apps.api.db.session import get_db
from apps.api.settings import settings

_bearer = HTTPBearer()


def _decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.nextauth_secret, algorithms=["HS256"])
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = _decode_token(creds.credentials)
    email: str | None = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Token missing email claim")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        # Auto-provision on first login
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=payload.get("name"),
            daily_quota=settings.daily_message_quota,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..schemas import XiaomiLoginRequest
from ..xiaomi import service
from ..xiaomi.client import ApiError

logger = logging.getLogger("mooncare.xiaomi")
router = APIRouter(prefix="/api/xiaomi", tags=["xiaomi"])


@router.get("/status")
def xiaomi_status() -> dict:
    return service.status()


@router.post("/login")
def xiaomi_login(payload: XiaomiLoginRequest) -> dict:
    try:
        return service.login(
            username=payload.username,
            password=payload.password,
            region=payload.region,
            captcha=payload.captcha,
            twofa_code=payload.twofa_code,
            attempt_id=payload.attempt_id,
        )
    except service.XiaomiError as exc:
        logger.warning("小米登录失败：%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/logout")
def xiaomi_logout() -> dict:
    return service.logout()


@router.post("/sync")
def xiaomi_sync(days: int = Query(default=7, ge=1, le=service.MAX_SYNC_DAYS)) -> dict:
    try:
        return service.sync(days)
    except service.NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except service.XiaomiError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApiError as exc:
        raise HTTPException(status_code=502, detail=f"小米云端请求失败：{exc}") from exc

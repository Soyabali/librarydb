from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.deps import DB, AdminUser, CurrentUser
from app.core.exceptions import BadRequest, NotFound
from app.models import LibrarySetting
from app.schemas.reports import SettingRead, SettingUpdate
from app.services import library_settings as cfg
from app.services.activity import log_activity

router = APIRouter(prefix="/settings", tags=["Library settings"])


@router.get("", response_model=list[SettingRead], summary="All library settings")
def list_settings(db: DB, _: CurrentUser):
    return db.scalars(select(LibrarySetting).order_by(LibrarySetting.setting_key)).all()


@router.get("/{key}", response_model=SettingRead, summary="One setting")
def get_setting(key: str, db: DB, _: CurrentUser):
    setting = db.scalar(select(LibrarySetting).where(LibrarySetting.setting_key == key))
    if setting is None:
        raise NotFound("Setting", key)
    return setting


@router.put("/{key}", response_model=SettingRead, summary="Change a setting (admin)")
def update_setting(key: str, payload: SettingUpdate, db: DB, admin: AdminUser, request: Request):
    setting = db.scalar(select(LibrarySetting).where(LibrarySetting.setting_key == key))
    if setting is None:
        raise NotFound("Setting", key)
    value = payload.setting_value.strip()
    if error := cfg.validate_value(key, value):
        raise BadRequest(error)
    old = setting.setting_value
    setting.setting_value = value
    setting.updated_at = func.now()
    log_activity(db, user=admin, action="SETTING_UPDATED", description=f"{key}: '{old}' -> '{value}'",
                 request=request)
    db.commit()
    db.refresh(setting)
    return setting

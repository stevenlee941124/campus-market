import os
import shutil
import urllib.parse
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import jwt
from sqlalchemy.orm import Session

import auth_utils
import database
import models

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="templates")


def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return jwt.decode(
            token.replace("Bearer ", ""),
            auth_utils.SECRET_KEY,
            algorithms=[auth_utils.ALGORITHM],
        )
    except Exception:
        return None


def save_avatar_file(file: UploadFile) -> str:
    os.makedirs("static/uploads", exist_ok=True)
    safe_name = f"avatar_{uuid4().hex}_{os.path.basename(file.filename)}"
    file_location = f"static/uploads/{safe_name}"
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    return f"/static/uploads/{safe_name}"


@router.get("")
@router.get("/")
def settings_page(
    request: Request,
    error: str = Query(None),
    success: str = Query(None),
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    user_id = user.get("user_id")
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "db_user": db_user,
            "error": error,
            "success": success
        }
    )


@router.post("")
@router.post("/")
async def update_settings(
    request: Request,
    nickname: str = Form(...),
    bio: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    user_id = user.get("user_id")
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="找不到使用者")

    db_user.nickname = nickname.strip()
    db_user.bio = bio.strip()

    if file and file.filename:
        db_user.avatar = save_avatar_file(file)

    db.commit()
    
    # 重新跳轉回設定頁，帶上成功提示
    return RedirectResponse(url="/settings?success=1", status_code=303)


@router.post("/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(database.get_db),
    user = Depends(get_current_user)
):
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    user_id = user.get("user_id")
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="找不到使用者")

    # 1. 驗證目前密碼是否正確
    if not auth_utils.verify_password(current_password, db_user.password_hash):
        err_msg = urllib.parse.quote("目前密碼輸入錯誤，請重新確認。")
        return RedirectResponse(url=f"/settings?error={err_msg}", status_code=303)

    # 2. 驗證新密碼長度與一致性
    if len(new_password) < 6:
        err_msg = urllib.parse.quote("新密碼長度至少需要 6 個字元。")
        return RedirectResponse(url=f"/settings?error={err_msg}", status_code=303)

    if new_password != confirm_password:
        err_msg = urllib.parse.quote("兩次輸入的新密碼不一致，請重新輸入。")
        return RedirectResponse(url=f"/settings?error={err_msg}", status_code=303)

    # 3. 更新密碼
    db_user.password_hash = auth_utils.get_password_hash(new_password)
    db.commit()

    success_msg = urllib.parse.quote("密碼已變更成功！請妥善保管您的新密碼。")
    return RedirectResponse(url=f"/settings?success={success_msg}", status_code=303)

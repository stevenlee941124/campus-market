from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from jose import jwt
from sqlalchemy.orm import Session

import auth_utils
import database
import models


router = APIRouter(prefix="/search", tags=["search"])
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


@router.get("/")
def search_products(
    request: Request,
    q: str = "",
    cat: str = "",
    min_p: float = 0,
    max_p: float = 999999,
    db: Session = Depends(database.get_db),
):
    user = get_current_user(request)
    query = db.query(models.Product).filter(
        models.Product.price >= min_p,
        models.Product.price <= max_p,
    )

    if q:
        query = query.filter(
            (models.Product.name.contains(q)) | (models.Product.tags.contains(q))
        )
    if cat:
        query = query.filter(models.Product.category == cat)

    products = query.all()
    title_parts = []
    if q:
        title_parts.append(f"關鍵字：{q}")
    if cat:
        title_parts.append(f"分類：{cat}")
    title = "搜尋結果"
    if title_parts:
        title += " - " + "，".join(title_parts)

    return templates.TemplateResponse(
        "category.html",
        {
            "request": request,
            "products": products,
            "current_category": title,
            "user": user,
        },
    )

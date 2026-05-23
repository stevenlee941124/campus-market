import os
import shutil
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import jwt
from sqlalchemy.orm import Session

import auth_utils
import database
import models
from product_options import PRODUCT_CATEGORIES


router = APIRouter(prefix="/products", tags=["products"])
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


def save_upload(file: UploadFile) -> str:
    os.makedirs("static/uploads", exist_ok=True)
    safe_name = f"{uuid4().hex}_{os.path.basename(file.filename)}"
    file_location = f"static/uploads/{safe_name}"
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    return f"/static/uploads/{safe_name}"


@router.get("/")
def get_products(request: Request, category: str = None, db: Session = Depends(database.get_db)):
    user = get_current_user(request)
    query = db.query(models.Product)
    if category:
        query = query.filter(models.Product.category == category)
    products = query.all()
    return templates.TemplateResponse(
        "category.html",
        {
            "request": request,
            "products": products,
            "current_category": category or "全部商品",
            "user": user,
            "categories": PRODUCT_CATEGORIES,
        },
    )


@router.get("/{product_id}")
def get_product_detail(request: Request, product_id: int, db: Session = Depends(database.get_db)):
    user = get_current_user(request)
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    return templates.TemplateResponse("detail.html", {"request": request, "product": product, "user": user})


@router.post("/")
async def create_product(
    request: Request,
    name: str = Form(...),
    price: float = Form(...),
    category: str = Form(...),
    tags: str = Form(""),
    location: str = Form(...),
    contact_type: str = Form(...),
    contact: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    new_product = models.Product(
        name=name,
        price=price,
        category=category,
        tags=tags,
        location=location,
        contact_type=contact_type,
        contact=contact,
        description=description,
        image=save_upload(file),
        owner_id=user.get("user_id"),
    )
    db.add(new_product)
    db.commit()
    return RedirectResponse(url="/seller/dashboard", status_code=303)


@router.get("/{product_id}/edit")
def edit_product_page(request: Request, product_id: int, db: Session = Depends(database.get_db)):
    user = get_current_user(request)
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not user or not product or product.owner_id != user.get("user_id"):
        raise HTTPException(status_code=403, detail="權限不足")
    return templates.TemplateResponse(
        "edit.html",
        {
            "request": request,
            "product": product,
            "user": user,
            "categories": PRODUCT_CATEGORIES,
        },
    )


@router.post("/{product_id}/edit")
async def update_product(
    request: Request,
    product_id: int,
    name: str = Form(...),
    price: float = Form(...),
    category: str = Form(...),
    tags: str = Form(""),
    location: str = Form(...),
    contact_type: str = Form(...),
    contact: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(database.get_db),
):
    user = get_current_user(request)
    product = db.query(models.Product).filter(models.Product.id == product_id).first()

    if not user or not product or product.owner_id != user.get("user_id"):
        raise HTTPException(status_code=403, detail="權限不足")

    product.name = name
    product.price = price
    product.category = category
    product.location = location
    product.tags = tags
    product.description = description
    product.contact_type = contact_type
    product.contact = contact

    if file and file.filename:
        product.image = save_upload(file)

    db.commit()
    return RedirectResponse(url="/seller/dashboard", status_code=303)


@router.post("/{product_id}/delete")
def delete_product(request: Request, product_id: int, db: Session = Depends(database.get_db)):
    user = get_current_user(request)
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not user or not product or product.owner_id != user.get("user_id"):
        raise HTTPException(status_code=403, detail="權限不足")
    db.delete(product)
    db.commit()
    return RedirectResponse(url="/seller/dashboard", status_code=303)

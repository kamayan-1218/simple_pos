from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import logging
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from .config import settings
from .database import Base, engine, get_db
from .models import (Member, Product, Sale, SaleItem, StaffQrCredential,
                     StaffUser, TaxRate, utcnow)
from .schemas import LoginInput, QrLoginInput, RefreshInput, SaleInput
from .security import (current_staff, digest, hasher, invalid_auth, issue_tokens,
                       revoke_refresh, rotate_refresh)

app = FastAPI(title="POS API", docs_url=None if settings.environment == "production" else "/docs",
              redoc_url=None if settings.environment == "production" else "/redoc",
              openapi_url=None if settings.environment == "production" else "/openapi.json")
log = logging.getLogger("pos.api")

@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "ERROR", "message": "操作に失敗しました"}
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": {**detail, "error_id": uuid4().hex}})

@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, _exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": {"code": "VALIDATION_ERROR",
                        "message": "入力値を確認してください", "error_id": uuid4().hex}})

@app.exception_handler(SQLAlchemyError)
async def database_error(_request: Request, exc: SQLAlchemyError):
    error_id = uuid4().hex
    log.error("Database error id=%s type=%s", error_id, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": {"code": "DB_UNAVAILABLE",
                        "message": "データベースに接続できません", "error_id": error_id}})

@app.exception_handler(Exception)
async def unexpected_error(_request: Request, exc: Exception):
    error_id = uuid4().hex
    log.error("Unexpected server error id=%s type=%s", error_id, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": {"code": "INTERNAL_ERROR",
                        "message": "処理できませんでした", "error_id": error_id}})

def fail(status: int, code: str, message: str):
    raise HTTPException(status, detail={"code": code, "message": message})

def active_tax(db: Session) -> TaxRate:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    rate = (db.query(TaxRate).filter(TaxRate.is_active.is_(True),
            TaxRate.effective_from <= today,
            or_(TaxRate.effective_to.is_(None), TaxRate.effective_to >= today))
            .order_by(TaxRate.effective_from.desc()).first())
    if not rate:
        fail(503, "TAX_RATE_UNAVAILABLE", "有効な税率がありません")
    return rate

def sale_response(sale: Sale) -> dict:
    return {"transaction_id": sale.id, "sold_at": sale.sold_at.isoformat() + "Z",
            "server_totals": {"subtotal_excl_tax": int(sale.subtotal_excl_tax),
                              "tax_amount": int(sale.tax_amount),
                              "total_incl_tax": int(sale.total_incl_tax)}}

@app.get("/v1/health")
def health():
    return {"status": "ok"}

@app.post("/v1/auth/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    staff = db.query(StaffUser).filter_by(staff_code=data.staff_code, is_active=True).first()
    if not staff:
        invalid_auth()
    try:
        hasher.verify(staff.password_hash, data.password)
    except Exception:
        invalid_auth()
    return issue_tokens(db, staff)

@app.post("/v1/auth/qr-login")
def qr_login(data: QrLoginInput, db: Session = Depends(get_db)):
    credential = db.query(StaffQrCredential).filter_by(token_hash=digest(data.qr_token), revoked_at=None).first()
    if not credential or (credential.expires_at and credential.expires_at <= utcnow()):
        invalid_auth()
    staff = db.get(StaffUser, credential.staff_user_id)
    if not staff or not staff.is_active:
        invalid_auth()
    return issue_tokens(db, staff)

@app.post("/v1/auth/refresh")
def refresh(data: RefreshInput, db: Session = Depends(get_db)):
    return rotate_refresh(db, data.refresh_token)

@app.post("/v1/auth/logout")
def logout(data: RefreshInput, db: Session = Depends(get_db)):
    revoke_refresh(db, data.refresh_token)
    return {"success": True}

@app.get("/v1/auth/me")
def me(staff: StaffUser = Depends(current_staff)):
    return {"id": staff.id, "staff_code": staff.staff_code, "display_name": staff.display_name}

@app.get("/v1/members/{member_code}")
def member(member_code: str, db: Session = Depends(get_db), staff: StaffUser = Depends(current_staff)):
    if not 1 <= len(member_code) <= 50:
        fail(422, "VALIDATION_ERROR", "会員IDの長さが正しくありません")
    found = db.query(Member).filter_by(member_code=member_code, is_active=True).first()
    if not found:
        fail(404, "MEMBER_NOT_FOUND", "会員が登録されていません")
    return {"member_code": found.member_code, "name": found.name}

@app.get("/v1/products/{product_code}")
def product(product_code: str, db: Session = Depends(get_db), staff: StaffUser = Depends(current_staff)):
    if not 1 <= len(product_code) <= 50:
        fail(422, "VALIDATION_ERROR", "商品コードの長さが正しくありません")
    found = db.query(Product).filter_by(product_code=product_code, is_active=True).first()
    if not found:
        fail(404, "PRODUCT_NOT_FOUND", "商品がマスタ未登録です")
    if (found.unit_price_excl_tax < 0 or found.unit_price_excl_tax != found.unit_price_excl_tax.to_integral_value() or
            found.unit_price_excl_tax > Decimal("9999999")):
        fail(422, "VALIDATION_ERROR", "商品の税抜単価は0～9,999,999円の整数にしてください")
    return {"code": found.product_code, "name": found.name, "size": found.size,
            "unit_price_excl_tax": int(found.unit_price_excl_tax)}

@app.get("/v1/settings/tax-rate")
def tax_rate(db: Session = Depends(get_db), staff: StaffUser = Depends(current_staff)):
    rate = active_tax(db)
    return {"rate": str(rate.rate), "effective_from": rate.effective_from.isoformat()}

@app.post("/v1/transactions")
def create_sale(data: SaleInput, db: Session = Depends(get_db), staff: StaffUser = Depends(current_staff)):
    key = str(data.idempotency_key)
    existing = db.query(Sale).filter_by(idempotency_key=key).first()
    if existing:
        if existing.staff_user_id != staff.id:
            fail(409, "DUPLICATE_TRANSACTION", "別の担当者による取引キーです")
        return sale_response(existing)
    member = None
    if data.member_code:
        member = db.query(Member).filter_by(member_code=data.member_code, is_active=True).first()
        if not member:
            fail(404, "MEMBER_NOT_FOUND", "会員が登録されていません")
    rate = active_tax(db)
    lines = []
    subtotal = 0
    for item in data.items:
        found = db.query(Product).filter_by(product_code=item.product_code, is_active=True).first()
        if not found:
            fail(404, "PRODUCT_NOT_FOUND", "商品がマスタ未登録です")
        price = found.unit_price_excl_tax
        # Initial design decision: all POS prices are whole yen.
        if price < 0 or price != price.to_integral_value() or price > Decimal("9999999"):
            fail(422, "VALIDATION_ERROR", "商品の税抜単価は0～9,999,999円の整数にしてください")
        subtotal += int(price)
        lines.append((item, found, price))
    tax = int((Decimal(subtotal) * rate.rate).to_integral_value(rounding=ROUND_FLOOR))
    total = subtotal + tax
    if total > 99_999_999:
        fail(422, "VALIDATION_ERROR", "取引金額が上限を超えています")
    if data.client_totals.model_dump() != {"subtotal_excl_tax": subtotal,
                                           "tax_amount": tax, "total_incl_tax": total}:
        fail(409, "CALCULATION_MISMATCH", "金額が更新されました。再確認してください")
    sale = Sale(id=str(uuid4()), idempotency_key=key, member_id=member.id if member else None,
                staff_user_id=staff.id, tax_rate_id=rate.id, sold_at=utcnow(),
                subtotal_excl_tax=Decimal(subtotal), tax_amount=Decimal(tax),
                total_incl_tax=Decimal(total), customer_type="MEMBER" if member else "NON_MEMBER")
    for item, found, price in lines:
        sale.items.append(SaleItem(line_no=item.line_no, product_id=found.id,
            product_code_snapshot=found.product_code, product_name_snapshot=found.name,
            size_snapshot=found.size, unit_price_excl_tax=price,
            quantity=1, line_subtotal=price))
    try:
        db.add(sale)
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = db.query(Sale).filter_by(idempotency_key=key).first()
        if prior and prior.staff_user_id == staff.id:
            return sale_response(prior)
        fail(409, "DUPLICATE_TRANSACTION", "取引が重複しました")
    except SQLAlchemyError:
        db.rollback()
        fail(503, "DB_UNAVAILABLE", "保存できませんでした。再試行してください")
    return sale_response(sale)

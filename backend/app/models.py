from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class StaffUser(Base):
    __tablename__ = "staff_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_code: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="CASHIER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class StaffQrCredential(Base):
    __tablename__ = "staff_qr_credential"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)

class RefreshToken(Base):
    __tablename__ = "auth_refresh_token"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Member(Base):
    __tablename__ = "member"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(String(255))
    gender: Mapped[str | None] = mapped_column(String(20))
    age: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Product(Base):
    __tablename__ = "product"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    size: Mapped[str | None] = mapped_column(String(50))
    unit_price_excl_tax: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class TaxRate(Base):
    __tablename__ = "tax_rate"
    id: Mapped[int] = mapped_column(primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Sale(Base):
    __tablename__ = "sales_transaction"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("member.id"))
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    tax_rate_id: Mapped[int] = mapped_column(ForeignKey("tax_rate.id"))
    sold_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    subtotal_excl_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_incl_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    customer_type: Mapped[str] = mapped_column(String(20))
    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")

class SaleItem(Base):
    __tablename__ = "sales_transaction_item"
    __table_args__ = (UniqueConstraint("transaction_id", "line_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("sales_transaction.id"))
    line_no: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    product_code_snapshot: Mapped[str] = mapped_column(String(50))
    product_name_snapshot: Mapped[str] = mapped_column(String(100))
    size_snapshot: Mapped[str | None] = mapped_column(String(50))
    unit_price_excl_tax: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sale: Mapped[Sale] = relationship(back_populates="items")

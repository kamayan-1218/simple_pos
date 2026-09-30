from uuid import UUID
from pydantic import BaseModel, Field, field_validator

Code = Field(min_length=1, max_length=50)

class LoginInput(BaseModel):
    staff_code: str = Code
    password: str = Field(min_length=8, max_length=64)

class QrLoginInput(BaseModel):
    qr_token: str = Field(min_length=32, max_length=256)

class RefreshInput(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)

class ItemInput(BaseModel):
    line_no: int = Field(ge=1, le=100)
    product_code: str = Code

class ClientTotals(BaseModel):
    subtotal_excl_tax: int = Field(ge=0, le=99_999_999)
    tax_amount: int = Field(ge=0, le=99_999_999)
    total_incl_tax: int = Field(ge=0, le=99_999_999)

class SaleInput(BaseModel):
    idempotency_key: UUID
    member_code: str | None = Field(default=None, min_length=1, max_length=50)
    items: list[ItemInput] = Field(min_length=1, max_length=100)
    client_totals: ClientTotals

    @field_validator("items")
    @classmethod
    def unique_lines(cls, items):
        if len({item.line_no for item in items}) != len(items):
            raise ValueError("line_no must be unique")
        return items

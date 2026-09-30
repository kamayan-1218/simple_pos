"""Local demonstration data. Run from backend: python -m app.seed"""
import getpass
import secrets
from pathlib import Path
import qrcode
from datetime import date
from decimal import Decimal
from .database import Base, SessionLocal, engine
from .models import Member, Product, StaffQrCredential, StaffUser, TaxRate
from .security import digest, hasher

def main():
    Base.metadata.create_all(engine)
    qr_dir = Path('dev_qr')
    qr_dir.mkdir(exist_ok=True)
    with SessionLocal() as db:
        staff = db.query(StaffUser).filter_by(staff_code="cashier01").first()
        if not staff:
            password = getpass.getpass("cashier01 のパスワード（8文字以上）: ")
            if not 8 <= len(password) <= 64:
                raise ValueError("8～64文字にしてください")
            staff = StaffUser(staff_code="cashier01", display_name="レジ担当者", password_hash=hasher.hash(password))
            db.add(staff)
            db.flush()
            token = secrets.token_urlsafe(32)
            db.add(StaffQrCredential(staff_user_id=staff.id, token_hash=digest(token)))
            print("担当者QRの値（再表示不可、秘密として管理）:", token)
            qrcode.make(token).save(qr_dir / 'staff_cashier01.png')
        if not db.query(Member).filter_by(member_code="M001").first():
            db.add(Member(member_code="M001", name="テスト会員"))
        for code, name, yen in [("P101", "テスト商品A", 101), ("P250", "テスト商品B", 250), ("P000", "0円商品", 0)]:
            if not db.query(Product).filter_by(product_code=code).first():
                db.add(Product(product_code=code, name=name, size="標準", unit_price_excl_tax=Decimal(yen)))
        if not db.query(TaxRate).first():
            db.add(TaxRate(rate=Decimal("0.1000"), effective_from=date(2020, 1, 1)))
        db.commit()
    qrcode.make('M001').save(qr_dir / 'member_M001.png')
    for code in ('P101', 'P250', 'P000'):
        qrcode.make(code).save(qr_dir / f'product_{code}.png')
    print("開発用データを準備しました: 会員 M001、商品 P101/P250/P000")
    print("QR画像: backend/dev_qr（担当者QRは秘密情報として管理）")

if __name__ == "__main__":
    main()

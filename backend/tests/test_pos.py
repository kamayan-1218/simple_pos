from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.models import Member, Product, Sale, SaleItem, StaffQrCredential, StaffUser, TaxRate
from app.security import digest, hasher

@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as db:
        db.add_all([
            StaffUser(staff_code='cashier', display_name='担当者', password_hash=hasher.hash('test-password')),
            Member(member_code='M001', name='会員'),
            Product(product_code='P101', name='商品', size='標準', unit_price_excl_tax=Decimal('101')),
            TaxRate(rate=Decimal('0.1000'), effective_from=date(2020, 1, 1)),
        ])
        db.flush()
        staff = db.scalar(select(StaffUser))
        db.add(StaffQrCredential(staff_user_id=staff.id, token_hash=digest('q' * 40)))
        db.commit()
    def override():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as http:
        yield http, Session
    app.dependency_overrides.clear()
    engine.dispose()

def auth(http):
    response = http.post('/v1/auth/login', json={'staff_code': 'cashier', 'password': 'test-password'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token']}

def payload(key=None, member='M001', items=None, totals=None):
    return {'idempotency_key': key or str(uuid4()), 'member_code': member,
            'items': items or [{'line_no': 1, 'product_code': 'P101'}],
            'client_totals': totals or {'subtotal_excl_tax': 101, 'tax_amount': 10, 'total_incl_tax': 111}}

def test_login_and_lookup(client):
    http, _ = client
    assert http.post('/v1/auth/login', json={'staff_code': 'cashier', 'password': 'wrong-password'}).status_code == 401
    headers = auth(http)
    assert http.get('/v1/members/M001', headers=headers).json()['name'] == '会員'
    assert http.get('/v1/products/P101', headers=headers).json()['unit_price_excl_tax'] == 101
    assert http.get('/v1/members/unknown', headers=headers).status_code == 404
    assert http.get('/v1/products/' + 'x' * 51, headers=headers).status_code == 422
    assert http.get('/v1/products/P101').status_code == 401

def test_sale_and_idempotency(client):
    http, Session = client
    headers = auth(http)
    data = payload()
    first = http.post('/v1/transactions', json=data, headers=headers)
    second = http.post('/v1/transactions', json=data, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()['server_totals'] == {'subtotal_excl_tax': 101, 'tax_amount': 10, 'total_incl_tax': 111}
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Sale)) == 1
        assert db.scalar(select(func.count()).select_from(SaleItem)) == 1
        assert db.scalar(select(SaleItem.product_name_snapshot)) == '商品'

def test_rejects_bad_totals_and_101_items(client):
    http, Session = client
    headers = auth(http)
    bad = payload(totals={'subtotal_excl_tax': 101, 'tax_amount': 11, 'total_incl_tax': 112})
    assert http.post('/v1/transactions', json=bad, headers=headers).status_code == 409
    many = payload(items=[{'line_no': i + 1, 'product_code': 'P101'} for i in range(101)])
    assert http.post('/v1/transactions', json=many, headers=headers).status_code == 422
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Sale)) == 0

def test_two_scans_are_two_items_and_nonmember(client):
    http, Session = client
    headers = auth(http)
    data = payload(member=None, items=[{'line_no': 1, 'product_code': 'P101'}, {'line_no': 2, 'product_code': 'P101'}],
                   totals={'subtotal_excl_tax': 202, 'tax_amount': 20, 'total_incl_tax': 222})
    assert http.post('/v1/transactions', json=data, headers=headers).status_code == 200
    with Session() as db:
        sale = db.scalar(select(Sale))
        assert sale.customer_type == 'NON_MEMBER'
        assert len(sale.items) == 2

def test_qr_refresh_and_revoke(client):
    http, _ = client
    assert http.post('/v1/auth/qr-login', json={'qr_token': 'x' * 40}).status_code == 401
    response = http.post('/v1/auth/qr-login', json={'qr_token': 'q' * 40})
    assert response.status_code == 200
    original = response.json()['refresh_token']
    renewed = http.post('/v1/auth/refresh', json={'refresh_token': original})
    assert renewed.status_code == 200
    assert http.post('/v1/auth/refresh', json={'refresh_token': original}).status_code == 401
    successor = renewed.json()['refresh_token']
    assert http.post('/v1/auth/logout', json={'refresh_token': successor}).status_code == 200
    assert http.post('/v1/auth/refresh', json={'refresh_token': successor}).status_code == 401

def test_duplicate_lines_and_missing_product_do_not_save(client):
    http, Session = client
    headers = auth(http)
    same_line = payload(items=[{'line_no': 1, 'product_code': 'P101'}, {'line_no': 1, 'product_code': 'P101'}])
    assert http.post('/v1/transactions', json=same_line, headers=headers).status_code == 422
    missing = payload(items=[{'line_no': 1, 'product_code': 'UNKNOWN'}])
    assert http.post('/v1/transactions', json=missing, headers=headers).status_code == 404
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Sale)) == 0

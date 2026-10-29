from datetime import date, timedelta
from decimal import Decimal

import pytest

from rates.models import Currency, ExchangeRate

LAST_DAY = date(2026, 10, 27)


@pytest.fixture
def usd(db):
    return Currency.objects.create(code="USD", numeric_code=840, name="Долар США")


@pytest.fixture
def eur(db):
    return Currency.objects.create(code="EUR", numeric_code=978, name="Євро")


@pytest.fixture
def rates(usd, eur):
    """Ten days of rates ending on LAST_DAY. USD rises 0.1 per day, EUR stays flat."""
    rows = []
    for offset in range(10):
        day = LAST_DAY - timedelta(days=9 - offset)
        rows.append(
            ExchangeRate(currency=usd, date=day, rate=Decimal("41.0") + Decimal("0.1") * offset)
        )
        rows.append(ExchangeRate(currency=eur, date=day, rate=Decimal("48.0")))
    ExchangeRate.objects.bulk_create(rows)
    return rows


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="andrii", password="s3cret-pass-123")

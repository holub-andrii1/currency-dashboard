from datetime import timedelta
from decimal import Decimal

import pytest

from rates.services.analytics import (
    RateNotFound,
    convert,
    currency_stats,
    daily_changes,
    latest_date,
    rate_series,
)

from .conftest import LAST_DAY

pytestmark = pytest.mark.django_db


def test_latest_date(rates):
    assert latest_date() == LAST_DAY


def test_convert_foreign_to_uah(rates):
    result = convert(Decimal("100"), "USD", "UAH")
    assert result.result == Decimal("4190.00")  # 100 * 41.9
    assert result.date == LAST_DAY


def test_convert_uah_to_foreign(rates):
    result = convert(Decimal("4800"), "UAH", "EUR")
    assert result.result == Decimal("100.00")


def test_convert_cross_rate(rates):
    result = convert(Decimal("48"), "EUR", "usd")
    assert result.to_code == "USD"
    assert result.result == Decimal("54.99")  # 48 * 48 / 41.9


def test_convert_uses_closest_earlier_date(rates):
    future = LAST_DAY + timedelta(days=30)
    assert convert(Decimal("1"), "USD", "UAH", future).date == LAST_DAY

    first_day = LAST_DAY - timedelta(days=9)
    assert convert(Decimal("1"), "USD", "UAH", first_day).result == Decimal("41.00")


def test_convert_raises_when_no_rate(rates):
    with pytest.raises(RateNotFound):
        convert(Decimal("1"), "USD", "UAH", LAST_DAY - timedelta(days=100))


def test_rate_series_is_ordered(usd, rates):
    series = rate_series(usd, LAST_DAY - timedelta(days=2), LAST_DAY)
    assert [point["rate"] for point in series] == [
        Decimal("41.7"),
        Decimal("41.8"),
        Decimal("41.9"),
    ]


def test_currency_stats(usd, rates):
    stats = currency_stats(usd, LAST_DAY - timedelta(days=9), LAST_DAY)
    assert stats.first == Decimal("41.0")
    assert stats.latest == Decimal("41.9")
    assert stats.change == Decimal("0.9000")
    assert stats.change_pct == Decimal("2.20")
    assert stats.minimum == Decimal("41.0")
    assert stats.maximum == Decimal("41.9")


def test_currency_stats_returns_none_without_data(usd):
    assert currency_stats(usd, LAST_DAY, LAST_DAY) is None


def test_daily_changes(usd, eur, rates):
    changes = {c.currency.code: c for c in daily_changes([usd, eur])}
    assert changes["USD"].change == Decimal("0.1")
    assert changes["USD"].change_pct == Decimal("0.24")
    assert changes["EUR"].change == Decimal("0")

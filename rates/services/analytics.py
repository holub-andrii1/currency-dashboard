"""Read-side logic: rate series, statistics and currency conversion.

The NBU publishes how many hryvnias (UAH) one unit of a foreign currency
costs, so UAH is the base currency with an implicit rate of 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Avg, Max, Min

from rates.models import Currency, ExchangeRate

BASE_CURRENCY = "UAH"
RATE_PRECISION = Decimal("0.000001")  # matches ExchangeRate.rate decimal_places


class RateNotFound(Exception):
    """No rate is stored for the requested currency on or before the date."""


def latest_date() -> date | None:
    return ExchangeRate.objects.aggregate(latest=Max("date"))["latest"]


def rate_on(code: str, on: date | None = None) -> tuple[Decimal, date]:
    """Rate of ``code`` in UAH on ``on`` (or the closest earlier day with data)."""
    code = code.upper()
    if code == BASE_CURRENCY:
        return Decimal("1"), on or date.today()

    queryset = ExchangeRate.objects.filter(currency__code=code)
    if on is not None:
        queryset = queryset.filter(date__lte=on)
    row = queryset.order_by("-date").values("rate", "date").first()
    if row is None:
        raise RateNotFound(f"No rate for {code}" + (f" on or before {on}" if on else ""))
    return row["rate"], row["date"]


@dataclass(frozen=True)
class Conversion:
    amount: Decimal
    from_code: str
    to_code: str
    result: Decimal
    rate: Decimal  # units of `to` for one unit of `from`
    date: date


def convert(amount: Decimal, from_code: str, to_code: str, on: date | None = None) -> Conversion:
    """Convert ``amount`` between any two currencies using UAH as the bridge."""
    from_rate, from_date = rate_on(from_code, on)
    to_rate, to_date = rate_on(to_code, on)
    cross_rate = from_rate / to_rate
    result = (amount * cross_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Report the date of the oldest real rate used (UAH has no stored rate).
    rate_dates = [
        rate_date
        for code, rate_date in ((from_code, from_date), (to_code, to_date))
        if code.upper() != BASE_CURRENCY
    ]
    used_date = min(rate_dates) if rate_dates else (on or date.today())
    return Conversion(
        amount=amount,
        from_code=from_code.upper(),
        to_code=to_code.upper(),
        result=result,
        rate=cross_rate.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        date=used_date,
    )


def rate_series(currency: Currency, start: date, end: date) -> list[dict]:
    """Daily rates of a currency between two dates, oldest first."""
    rows = currency.rates.filter(date__range=(start, end)).order_by("date")
    return [{"date": row.date, "rate": row.rate} for row in rows]


@dataclass(frozen=True)
class CurrencyStats:
    latest: Decimal
    latest_date: date
    first: Decimal
    change: Decimal
    change_pct: Decimal
    minimum: Decimal
    maximum: Decimal
    average: Decimal


def currency_stats(currency: Currency, start: date, end: date) -> CurrencyStats | None:
    """Summary statistics for a currency over a period, or None if no data."""
    rates = currency.rates.filter(date__range=(start, end))
    first = rates.order_by("date").first()
    last = rates.order_by("-date").first()
    if first is None or last is None:
        return None

    agg = rates.aggregate(minimum=Min("rate"), maximum=Max("rate"), average=Avg("rate"))
    change = last.rate - first.rate
    change_pct = (change / first.rate * 100) if first.rate else Decimal("0")
    return CurrencyStats(
        latest=last.rate,
        latest_date=last.date,
        first=first.rate,
        change=change.quantize(Decimal("0.0001")),
        change_pct=change_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        minimum=Decimal(agg["minimum"]).quantize(RATE_PRECISION),
        maximum=Decimal(agg["maximum"]).quantize(RATE_PRECISION),
        average=Decimal(agg["average"]).quantize(Decimal("0.0001")),
    )


@dataclass(frozen=True)
class DailyChange:
    currency: Currency
    rate: Decimal
    date: date
    change: Decimal | None
    change_pct: Decimal | None


def daily_changes(currencies) -> list[DailyChange]:
    """Latest rate of each currency and its change versus the previous day.

    Uses two queries in total (not two per currency): the NBU publishes all
    currencies every day, so we load the rows for the two most recent dates.
    Currencies without a rate on the latest date are left out.
    """
    currencies = list(currencies)
    recent_dates = list(
        ExchangeRate.objects.order_by("-date").values_list("date", flat=True).distinct()[:2]
    )
    if not recent_dates or not currencies:
        return []

    rows = ExchangeRate.objects.filter(currency__in=currencies, date__in=recent_dates)
    by_key = {(row.currency_id, row.date): row.rate for row in rows}
    latest = recent_dates[0]
    previous = recent_dates[1] if len(recent_dates) > 1 else None

    result = []
    for currency in currencies:
        rate = by_key.get((currency.pk, latest))
        if rate is None:
            continue
        prev_rate = by_key.get((currency.pk, previous))
        change = change_pct = None
        if prev_rate:
            change = rate - prev_rate
            change_pct = (change / prev_rate * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        result.append(DailyChange(currency, rate, latest, change, change_pct))
    return result

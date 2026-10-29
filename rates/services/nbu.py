"""Client for the National Bank of Ukraine exchange-rate API and DB sync.

API docs: https://bank.gov.ua/ua/open-data/api-dev
One request returns the official rates of all currencies for a single date:

    GET /NBUStatService/v1/statdirectory/exchange?date=YYYYMMDD&json
    [{"r030": 840, "txt": "Долар США", "rate": 41.2, "cc": "USD",
      "exchangedate": "28.10.2026"}, ...]
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction

from rates.models import Currency, ExchangeRate

logger = logging.getLogger(__name__)


class NBUError(Exception):
    """Raised when the NBU API is unreachable or returns unexpected data."""


@dataclass(frozen=True)
class RateRecord:
    code: str
    numeric_code: int
    name: str
    rate: Decimal
    date: date


def parse_rates(payload: object) -> list[RateRecord]:
    """Convert the raw JSON list returned by the NBU into RateRecord objects."""
    if not isinstance(payload, list):
        raise NBUError(f"Expected a JSON list, got {type(payload).__name__}")

    records = []
    for item in payload:
        try:
            records.append(
                RateRecord(
                    code=item["cc"].strip().upper(),
                    numeric_code=int(item["r030"]),
                    name=item["txt"].strip(),
                    # str() first so the float does not leak binary noise into Decimal
                    rate=Decimal(str(item["rate"])),
                    date=datetime.strptime(item["exchangedate"], "%d.%m.%Y").date(),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed NBU item %r: %s", item, exc)
    return records


def fetch_rates_for_date(day: date, session: requests.Session | None = None) -> list[RateRecord]:
    """Download the official rates of all currencies for one date."""
    http = session or requests
    try:
        response = http.get(
            settings.NBU_API_URL,
            params={"date": day.strftime("%Y%m%d"), "json": ""},
            timeout=settings.NBU_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NBUError(f"Failed to fetch rates for {day:%Y-%m-%d}: {exc}") from exc
    return parse_rates(payload)


def date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


@transaction.atomic
def save_records(records: list[RateRecord]) -> int:
    """Upsert currencies and rates. Returns the number of rate rows written."""
    if not records:
        return 0

    codes = {record.code for record in records}
    currencies = {c.code: c for c in Currency.objects.filter(code__in=codes)}
    for record in records:
        if record.code not in currencies:
            currencies[record.code] = Currency.objects.create(
                code=record.code, numeric_code=record.numeric_code, name=record.name
            )

    rows = [ExchangeRate(currency=currencies[r.code], date=r.date, rate=r.rate) for r in records]
    ExchangeRate.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["currency", "date"],
        update_fields=["rate"],
    )
    return len(rows)


@dataclass
class SyncResult:
    days_requested: int = 0
    days_fetched: int = 0
    rates_saved: int = 0
    failed_days: list[date] | None = None


def sync_rates(start: date, end: date, *, force: bool = False, workers: int = 8) -> SyncResult:
    """Download and store rates for every day in [start, end].

    Days that already have rates in the database are skipped unless
    ``force`` is True, so the command is cheap to run every day.
    Downloads run in parallel threads; database writes stay in this thread.
    """
    days = date_range(start, end)
    if not force:
        existing = set(
            ExchangeRate.objects.filter(date__range=(start, end))
            .values_list("date", flat=True)
            .distinct()
        )
        days = [day for day in days if day not in existing]

    result = SyncResult(days_requested=len(days), failed_days=[])
    if not days:
        return result

    with requests.Session() as session, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {day: pool.submit(fetch_rates_for_date, day, session) for day in days}
        for day, future in futures.items():
            try:
                records = future.result()
            except NBUError as exc:
                logger.error("%s", exc)
                result.failed_days.append(day)
                continue
            result.rates_saved += save_records(records)
            result.days_fetched += 1

    return result

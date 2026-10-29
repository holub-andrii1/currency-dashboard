from datetime import date
from decimal import Decimal

import pytest
import requests
from django.core.management import CommandError, call_command

from rates.models import Currency, ExchangeRate
from rates.services import nbu

SAMPLE = [
    {"r030": 840, "txt": "Долар США", "rate": 41.7823, "cc": "USD", "exchangedate": "27.10.2026"},
    {"r030": 978, "txt": "Євро", "rate": 48.196, "cc": "EUR", "exchangedate": "27.10.2026"},
]


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.response


def sample_for(day):
    return [{**item, "exchangedate": day.strftime("%d.%m.%Y")} for item in SAMPLE]


# --- parsing ---------------------------------------------------------------


def test_parse_rates_converts_fields():
    records = nbu.parse_rates(SAMPLE)
    assert records[0] == nbu.RateRecord(
        code="USD",
        numeric_code=840,
        name="Долар США",
        rate=Decimal("41.7823"),
        date=date(2026, 10, 27),
    )


def test_parse_rates_skips_malformed_items():
    payload = SAMPLE + [
        {"cc": "XXX"},
        {"r030": "x", "txt": "Bad", "rate": 1, "cc": "BAD", "exchangedate": "?"},
    ]
    assert [r.code for r in nbu.parse_rates(payload)] == ["USD", "EUR"]


def test_parse_rates_rejects_non_list():
    with pytest.raises(nbu.NBUError):
        nbu.parse_rates({"error": "oops"})


# --- HTTP ------------------------------------------------------------------


def test_fetch_rates_sends_date_in_nbu_format():
    session = FakeSession(FakeResponse(SAMPLE))
    records = nbu.fetch_rates_for_date(date(2026, 10, 27), session=session)
    assert len(records) == 2
    _, params = session.calls[0]
    assert params["date"] == "20261027"
    assert "json" in params


def test_fetch_rates_wraps_http_errors():
    session = FakeSession(FakeResponse([], status=503))
    with pytest.raises(nbu.NBUError):
        nbu.fetch_rates_for_date(date(2026, 10, 27), session=session)


# --- sync ------------------------------------------------------------------


@pytest.fixture
def fake_fetch(monkeypatch):
    calls = []

    def fetch(day, session=None):
        calls.append(day)
        if day == date(2026, 10, 3):
            raise nbu.NBUError("timeout")
        return nbu.parse_rates(sample_for(day))

    monkeypatch.setattr(nbu, "fetch_rates_for_date", fetch)
    return calls


@pytest.mark.django_db
def test_sync_saves_rates_and_reports_failures(fake_fetch):
    result = nbu.sync_rates(date(2026, 10, 1), date(2026, 10, 5), workers=2)

    assert result.days_requested == 5
    assert result.days_fetched == 4
    assert result.failed_days == [date(2026, 10, 3)]
    assert Currency.objects.count() == 2
    assert ExchangeRate.objects.count() == 8


@pytest.mark.django_db
def test_sync_skips_days_already_stored(fake_fetch):
    nbu.sync_rates(date(2026, 10, 1), date(2026, 10, 2))
    fake_fetch.clear()

    result = nbu.sync_rates(date(2026, 10, 1), date(2026, 10, 2))

    assert result.days_requested == 0
    assert fake_fetch == []


@pytest.mark.django_db
def test_save_records_updates_existing_rate():
    nbu.save_records(nbu.parse_rates(SAMPLE))
    corrected = [{**SAMPLE[0], "rate": 42.0}]
    nbu.save_records(nbu.parse_rates(corrected))

    usd_rate = ExchangeRate.objects.get(currency__code="USD", date=date(2026, 10, 27))
    assert usd_rate.rate == Decimal("42")
    assert ExchangeRate.objects.count() == 2


# --- management command ----------------------------------------------------


@pytest.mark.django_db
def test_fetch_rates_command(fake_fetch, capsys):
    call_command("fetch_rates", "--start", "2026-10-01", "--end", "2026-10-02")
    assert "Fetched 2/2 days" in capsys.readouterr().out


def test_fetch_rates_command_rejects_reversed_dates():
    with pytest.raises(CommandError):
        call_command("fetch_rates", "--start", "2026-10-05", "--end", "2026-10-01")

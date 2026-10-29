import pytest

from .conftest import LAST_DAY

pytestmark = pytest.mark.django_db


def test_currency_list(client, rates):
    data = client.get("/api/currencies/").json()
    usd = next(item for item in data if item["code"] == "USD")
    assert usd["latest_rate"] == "41.900000"
    assert usd["latest_date"] == LAST_DAY.isoformat()


def test_currency_detail_is_case_insensitive(client, rates):
    response = client.get("/api/currencies/usd/")
    assert response.status_code == 200
    assert response.json()["code"] == "USD"


def test_unknown_currency_returns_404(client, rates):
    assert client.get("/api/currencies/XYZ/").status_code == 404


def test_rates_for_period(client, rates):
    response = client.get(
        "/api/currencies/USD/rates/", {"start": "2026-10-25", "end": "2026-10-27"}
    )
    body = response.json()
    assert [r["rate"] for r in body["rates"]] == ["41.700000", "41.800000", "41.900000"]


def test_rates_reject_reversed_period(client, rates):
    response = client.get(
        "/api/currencies/USD/rates/", {"start": "2026-10-27", "end": "2026-10-01"}
    )
    assert response.status_code == 400


def test_stats(client, rates):
    body = client.get("/api/currencies/USD/stats/", {"days": 10}).json()
    assert body["change_pct"] == "2.20"
    assert body["max"] == "41.900000"


def test_stats_validates_days(client, rates):
    assert client.get("/api/currencies/USD/stats/", {"days": "abc"}).status_code == 400


def test_convert(client, rates):
    body = client.get("/api/convert/", {"amount": "100", "from": "USD", "to": "UAH"}).json()
    assert body["result"] == "4190.00"
    assert body["from"] == "USD"


def test_convert_unknown_currency(client, rates):
    response = client.get("/api/convert/", {"amount": "1", "from": "ABC", "to": "UAH"})
    assert response.status_code == 400


def test_convert_requires_params(client, rates):
    assert client.get("/api/convert/").status_code == 400

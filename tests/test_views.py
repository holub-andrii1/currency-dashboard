import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_dashboard_without_data_shows_instructions(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    assert b"fetch_rates" in response.content


def test_dashboard_shows_default_watchlist_and_chart(client, rates):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    assert response.context["currency"].code in {"USD", "EUR"}
    assert len(response.context["chart_data"]["values"]) == 10
    assert b"Popular currencies" in response.content


def test_dashboard_respects_currency_and_period(client, rates):
    response = client.get(reverse("dashboard"), {"currency": "EUR", "period": 30})
    assert response.context["currency"].code == "EUR"
    assert response.context["period"] == 30


def test_dashboard_ignores_invalid_params(client, rates):
    response = client.get(reverse("dashboard"), {"currency": "XYZ", "period": 7})
    assert response.status_code == 200


def test_currency_list_search(client, rates):
    response = client.get(reverse("currency_list"), {"q": "євро"})
    codes = [row.currency.code for row in response.context["rows"]]
    assert codes == ["EUR"]


def test_toggle_favorite_requires_login(client, rates):
    response = client.post(reverse("toggle_favorite", args=["USD"]))
    assert response.status_code == 302
    assert reverse("login") in response.url


def test_toggle_favorite_adds_and_removes(client, user, usd, rates):
    client.force_login(user)
    url = reverse("toggle_favorite", args=["usd"])

    client.post(url)
    assert list(user.favorite_currencies.values_list("code", flat=True)) == ["USD"]

    client.post(url)
    assert not user.favorite_currencies.exists()


def test_favorites_become_the_watchlist(client, user, eur, rates):
    eur.favorited_by.add(user)
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    assert [card.currency.code for card in response.context["cards"]] == ["EUR"]
    assert b"Your watchlist" in response.content


def test_toggle_favorite_blocks_open_redirect(client, user, rates):
    client.force_login(user)
    response = client.post(
        reverse("toggle_favorite", args=["USD"]), {"next": "https://evil.example"}
    )
    assert response.url == reverse("currency_list")


def test_converter_page(client, rates):
    response = client.get(
        reverse("converter"),
        {
            "amount": "100",
            "from_currency": "USD",
            "to_currency": "UAH",
        },
    )
    assert response.context["conversion"].result == 4190
    assert b"4190.00" in response.content


def test_converter_rejects_same_currency(client, rates):
    response = client.get(
        reverse("converter"),
        {
            "amount": "1",
            "from_currency": "USD",
            "to_currency": "USD",
        },
    )
    assert response.context["conversion"] is None
    assert b"two different currencies" in response.content


def test_signup_logs_user_in(client, django_user_model):
    response = client.post(
        reverse("signup"),
        {
            "username": "olena",
            "password1": "Very-strong-pass-42",
            "password2": "Very-strong-pass-42",
        },
    )
    assert response.status_code == 302
    assert django_user_model.objects.filter(username="olena").exists()
    assert "_auth_user_id" in client.session

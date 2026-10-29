from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import ChartForm, ConverterForm
from .models import Currency
from .services.analytics import (
    RateNotFound,
    convert,
    currency_stats,
    daily_changes,
    latest_date,
    rate_series,
)


def watchlist_for(user):
    """The user's favourite currencies, or the default watchlist."""
    if user.is_authenticated:
        favorites = user.favorite_currencies.all()
        if favorites.exists():
            return favorites
    return Currency.objects.filter(code__in=settings.DEFAULT_WATCHLIST)


def dashboard(request):
    last_day = latest_date()
    if last_day is None:
        return render(request, "rates/empty.html")

    watchlist = watchlist_for(request.user)
    default_code = watchlist.first().code if watchlist.exists() else Currency.objects.first().code

    form = ChartForm(request.GET or None, initial={"currency": default_code, "period": 90})
    if form.is_bound and form.is_valid():
        code, period = form.cleaned_data["currency"], form.cleaned_data["period"]
    else:
        code, period = default_code, 90

    currency = get_object_or_404(Currency, code=code)
    start = last_day - timedelta(days=period - 1)
    series = rate_series(currency, start, last_day)

    context = {
        "form": form if form.is_bound else ChartForm(initial={"currency": code, "period": period}),
        "currency": currency,
        "period": period,
        "stats": currency_stats(currency, start, last_day),
        "chart_data": {
            "labels": [point["date"].isoformat() for point in series],
            "values": [float(point["rate"]) for point in series],
            "code": currency.code,
        },
        "cards": daily_changes(watchlist),
        "is_custom_watchlist": request.user.is_authenticated
        and request.user.favorite_currencies.exists(),
        "latest_date": last_day,
    }
    return render(request, "rates/dashboard.html", context)


def currency_list(request):
    query = request.GET.get("q", "").strip()
    currencies = list(Currency.objects.all())
    if query:
        # Filter in Python: SQLite's icontains ignores case only for ASCII,
        # so "євро" would not match "Євро". The table has ~50 rows, so this is cheap.
        needle = query.casefold()
        currencies = [
            c for c in currencies if needle in c.code.casefold() or needle in c.name.casefold()
        ]

    favorite_ids = set()
    if request.user.is_authenticated:
        favorite_ids = set(request.user.favorite_currencies.values_list("pk", flat=True))

    return render(
        request,
        "rates/currency_list.html",
        {
            "rows": daily_changes(currencies),
            "query": query,
            "favorite_ids": favorite_ids,
            "latest_date": latest_date(),
        },
    )


@login_required
@require_POST
def toggle_favorite(request, code):
    currency = get_object_or_404(Currency, code=code.upper())
    if currency.favorited_by.filter(pk=request.user.pk).exists():
        currency.favorited_by.remove(request.user)
    else:
        currency.favorited_by.add(request.user)

    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("currency_list")


def converter(request):
    form = ConverterForm(request.GET or None)
    conversion = error = None
    if form.is_bound and form.is_valid():
        data = form.cleaned_data
        try:
            conversion = convert(
                data["amount"], data["from_currency"], data["to_currency"], data["date"]
            )
        except RateNotFound as exc:
            error = str(exc)
    return render(
        request,
        "rates/converter.html",
        {
            "form": form,
            "conversion": conversion,
            "error": error,
        },
    )

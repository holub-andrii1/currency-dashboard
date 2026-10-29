"""Read-only REST API built with Django REST Framework.

GET /api/currencies/                       all currencies with the latest rate
GET /api/currencies/{code}/                one currency
GET /api/currencies/{code}/rates/?start=&end=   daily rates (default: last 30 days)
GET /api/currencies/{code}/stats/?days=90  summary statistics
GET /api/convert/?amount=100&from=USD&to=EUR&date=2026-10-01
"""

from datetime import timedelta

from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .models import Currency, ExchangeRate
from .services.analytics import (
    BASE_CURRENCY,
    RateNotFound,
    convert,
    currency_stats,
    latest_date,
    rate_series,
)


class CurrencySerializer(serializers.ModelSerializer):
    latest_rate = serializers.DecimalField(max_digits=14, decimal_places=6, read_only=True)
    latest_date = serializers.DateField(read_only=True)

    class Meta:
        model = Currency
        fields = ["code", "numeric_code", "name", "latest_rate", "latest_date"]


def currencies_with_latest_rate():
    """Currencies annotated with their latest rate in a single SQL query."""
    latest = ExchangeRate.objects.filter(currency=OuterRef("pk")).order_by("-date")
    return Currency.objects.annotate(
        latest_rate=Subquery(latest.values("rate")[:1]),
        latest_date=Subquery(latest.values("date")[:1]),
    )


class RateQuerySerializer(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs.get("start") and attrs.get("end") and attrs["start"] > attrs["end"]:
            raise serializers.ValidationError("start must not be after end")
        return attrs


class ConvertQuerySerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0)
    from_ = serializers.CharField(max_length=3)
    to = serializers.CharField(max_length=3)
    date = serializers.DateField(required=False)

    def get_fields(self):
        # "from" is a Python keyword, so the field is declared as from_ and renamed here.
        fields = super().get_fields()
        fields["from"] = fields.pop("from_")
        return fields

    def validate(self, attrs):
        codes = {attrs["from"].upper(), attrs["to"].upper()} - {BASE_CURRENCY}
        known = set(Currency.objects.filter(code__in=codes).values_list("code", flat=True))
        unknown = codes - known
        if unknown:
            raise serializers.ValidationError(f"Unknown currency: {', '.join(sorted(unknown))}")
        return attrs


class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = currencies_with_latest_rate()
    serializer_class = CurrencySerializer
    lookup_field = "code"

    def get_object(self):
        return get_object_or_404(self.get_queryset(), code=self.kwargs["code"].upper())

    @action(detail=True)
    def rates(self, request, code=None):
        currency = self.get_object()
        query = RateQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        end = query.validated_data.get("end") or latest_date()
        if end is None:
            return Response({"currency": currency.code, "rates": []})
        start = query.validated_data.get("start") or end - timedelta(days=29)
        if start > end:
            raise ValidationError({"start": "start must not be after end"})

        series = rate_series(currency, start, end)
        return Response(
            {
                "currency": currency.code,
                "start": start,
                "end": end,
                "rates": [{"date": p["date"], "rate": str(p["rate"])} for p in series],
            }
        )

    @action(detail=True)
    def stats(self, request, code=None):
        currency = self.get_object()
        try:
            days = int(request.query_params.get("days", 90))
        except ValueError as exc:
            raise ValidationError({"days": "must be an integer"}) from exc
        if not 1 <= days <= 3650:
            raise ValidationError({"days": "must be between 1 and 3650"})

        end = latest_date()
        stats = currency_stats(currency, end - timedelta(days=days - 1), end) if end else None
        if stats is None:
            raise NotFound("No rates stored for this period")
        return Response(
            {
                "currency": currency.code,
                "days": days,
                "latest": str(stats.latest),
                "latest_date": stats.latest_date,
                "change": str(stats.change),
                "change_pct": str(stats.change_pct),
                "min": str(stats.minimum),
                "max": str(stats.maximum),
                "avg": str(stats.average),
            }
        )


@api_view(["GET"])
def convert_view(request):
    query = ConvertQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    data = query.validated_data
    try:
        result = convert(data["amount"], data["from"], data["to"], data.get("date"))
    except RateNotFound as exc:
        raise NotFound(str(exc)) from exc
    return Response(
        {
            "amount": str(result.amount),
            "from": result.from_code,
            "to": result.to_code,
            "rate": str(result.rate),
            "result": str(result.result),
            "date": result.date,
        }
    )

from django.conf import settings
from django.db import models


class Currency(models.Model):
    """A foreign currency published by the National Bank of Ukraine."""

    code = models.CharField(max_length=3, unique=True, help_text="ISO 4217 letter code, e.g. USD")
    numeric_code = models.PositiveSmallIntegerField(help_text="ISO 4217 numeric code (r030)")
    name = models.CharField(max_length=128, help_text="Name as published by the NBU")
    favorited_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="favorite_currencies", blank=True
    )

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "currencies"

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class ExchangeRate(models.Model):
    """Official NBU rate: how many UAH one unit of the currency costs on a date."""

    currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name="rates")
    date = models.DateField(db_index=True)
    rate = models.DecimalField(max_digits=14, decimal_places=6)

    class Meta:
        ordering = ["currency__code", "date"]
        constraints = [
            models.UniqueConstraint(fields=["currency", "date"], name="unique_rate_per_day"),
        ]

    def __str__(self) -> str:
        return f"{self.currency.code} {self.date:%Y-%m-%d}: {self.rate}"

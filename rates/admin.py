from django.contrib import admin

from .models import Currency, ExchangeRate


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "numeric_code", "name")
    search_fields = ("code", "name")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("currency", "date", "rate")
    list_filter = ("currency",)
    date_hierarchy = "date"
    list_select_related = ("currency",)

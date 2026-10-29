from decimal import Decimal

from django import forms

from .models import Currency
from .services.analytics import BASE_CURRENCY

PERIOD_CHOICES = [(30, "1 month"), (90, "3 months"), (180, "6 months"), (365, "1 year")]


def currency_choices(include_base: bool = False) -> list[tuple[str, str]]:
    choices = [(c.code, f"{c.code} — {c.name}") for c in Currency.objects.all()]
    if include_base:
        choices.insert(0, (BASE_CURRENCY, f"{BASE_CURRENCY} — Українська гривня"))
    return choices


class ChartForm(forms.Form):
    currency = forms.ChoiceField()
    period = forms.TypedChoiceField(choices=PERIOD_CHOICES, coerce=int, initial=90)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].choices = currency_choices()


class ConverterForm(forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=18, decimal_places=2, initial=100
    )
    from_currency = forms.ChoiceField(label="From", initial="USD")
    to_currency = forms.ChoiceField(label="To", initial=BASE_CURRENCY)
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Leave empty for the latest rate.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = currency_choices(include_base=True)
        self.fields["from_currency"].choices = choices
        self.fields["to_currency"].choices = choices

    def clean(self):
        cleaned = super().clean()
        source, target = cleaned.get("from_currency"), cleaned.get("to_currency")
        if source and source == target:
            raise forms.ValidationError("Choose two different currencies.")
        return cleaned

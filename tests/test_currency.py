from decimal import Decimal

import pytest

from spendwise.fx_provider.manual_provider import ManualFxProvider
from spendwise.money import convert, to_money


def test_to_money_rounds_correctly():
    assert to_money(10.005) == Decimal("10.01")
    assert to_money("19.999") == Decimal("20.00")
    assert to_money(5) == Decimal("5.00")


def test_convert_multiplies_and_rounds():
    result = convert(Decimal("100.00"), Decimal("3.75"))
    assert result == Decimal("375.00")


def test_manual_fx_same_currency_returns_rate_one():
    provider = ManualFxProvider()
    result = provider.get_rate("SAR", "SAR")
    assert result.rate == Decimal("1")
    assert result.source == "manual"


def test_manual_fx_requires_rate_for_other_currency():
    provider = ManualFxProvider()
    with pytest.raises(ValueError):
        provider.get_rate("USD", "SAR")


def test_manual_fx_uses_given_rate():
    provider = ManualFxProvider()
    result = provider.get_rate("USD", "SAR", manual_rate=Decimal("3.75"))
    assert result.rate == Decimal("3.75")

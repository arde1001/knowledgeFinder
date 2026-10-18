import pytest

from kf.pii import contains_pii


@pytest.mark.parametrize("text", [
    "write to anna.virtanen@example.org", "call +358 40 555 1234", "tel 040 555 1234",
    "IBAN FI12 3456 7890 1234 56", "address nothing but +358405551234",
])
def test_detects(text):
    assert contains_pii(text)


@pytest.mark.parametrize("text", [
    "Minutes covering 2024 2025 2026 events", "the 2024-2025 season", "Spring Gala 2025 budget of 12400 euros",
    "order number VB-4821-K",
])
def test_ignores_years_and_codes(text):
    assert not contains_pii(text)


from kf.pii import strip


def test_strip_replaces_each_kind():
    text = ("Mail anna.virtanen@example.org or call +358 40 555 1234. Lives at Koivukatu 12 B 7, 00100 Helsinki. "
            "Pay to FI12 3456 7890 1234 56.")
    out = strip(text)
    assert out == "Mail [email] or call [phone]. Lives at [address]. Pay to [iban]."


def test_strip_leaves_dates_amounts_years_and_codes():
    text = "Spring Gala 2025: budget 12400 euros, booked 2025-03-14, booking VB-4821-K, seasons 2024 2025 2026."
    assert strip(text) == text


def test_strip_catches_phone_and_postcode_variants():
    assert strip("call 040 555 1234") == "call [phone]"
    assert strip("Mantykuja 5, 00123 Helsinki") == "[address]"
    assert strip("Pihlajapolku 3 A") == "[address]"

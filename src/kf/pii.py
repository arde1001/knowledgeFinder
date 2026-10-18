"""Rule-based detection and removal of contact-style personal data: emails, phone numbers, IBANs, street addresses.

shortcut: street addresses are matched by common Finnish/Swedish/English street suffixes and 5-digit postcode + city;
unusual address formats and names are not covered. Upgrade to an NER model (e.g. Presidio) if recall on real data is poor.
"""

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d ()-]{7,}\d")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?\d{4}){2,}(?: ?\d{1,4})?\b")
YEARS = re.compile(r"(?:(?:19|20)\d\d[ -]*)+")  # "2024 2025", "2024-2025": a phone-shaped run of years
_STREET = r"[^\W\d_]+(?:katu|tie|kuja|polku|gatan|vagen|vägen|street|road|avenue|lane)"
ADDRESS = re.compile(rf"\b{_STREET}\s+\d+(?:\s?[A-Za-z])?(?:\s+\d+)?(?:,?\s*\d{{5}}\s+[A-Z][^\W\d_]+)?|\b\d{{5}}\s+[A-Z][^\W\d_]+")


def _is_phone(m):
    """Phone-shaped run that is not a run of years and is long enough not to be a date or an amount."""
    return not YEARS.fullmatch(m) and (m.startswith("+") or len(re.sub(r"\D", "", m)) >= 9)


def phones(text):
    return [m for m in PHONE.findall(text) if _is_phone(m)]


def contains_pii(text):
    return bool(EMAIL.search(text) or IBAN.search(text) or ADDRESS.search(text) or phones(text))


def strip(text):
    """Replace personal data with placeholders. Order matters: IBANs and addresses contain digit runs."""
    text = IBAN.sub("[iban]", text)
    text = EMAIL.sub("[email]", text)
    text = ADDRESS.sub("[address]", text)
    return PHONE.sub(lambda m: "[phone]" if _is_phone(m.group()) else m.group(), text)

"""Conservative cash-price and odometer extraction from a listing's source text."""

from __future__ import annotations

import re
from dataclasses import dataclass

NUMBER = r"(?:\d{1,3}(?:[,. ]\d{3})+(?:\.\d{2})?|\d{1,8}(?:\.\d{2})?)"
CURRENCY = r"(?:AED|DHS?\.?|DIRHAMS?)"
MONEY_RE = re.compile(
    rf"(?<!\w)(?:(?P<currency_before>{CURRENCY})\s*(?P<amount_after>{NUMBER})|"
    rf"(?P<amount_before>{NUMBER})\s*(?P<currency_after>{CURRENCY}))(?!\w)",
    re.IGNORECASE,
)
DISTANCE_RE = re.compile(
    rf"(?<![\w/])(?P<number>{NUMBER})\s*\(?\s*(?P<unit>km|kms|kilometres?|kilometers?)\b\)?",
    re.IGNORECASE,
)
AR_PRICE_RE = re.compile(
    rf"السعر\s*[:：]?\s*(?P<number>{NUMBER})\s*درهم", re.IGNORECASE
)
AR_MILEAGE_RE = re.compile(
    rf"(?:العداد|عداد\s+المسافات)\s*[:：]?\s*(?P<number>{NUMBER})\s*(?:كم|km)\b",
    re.IGNORECASE,
)
PRICE_MARKER_RE = re.compile(
    r"(?:selling|asking|cash|sale|offer|total)\s+price\s*[:\-]?\s*$|\bprice\s*[:\-]\s*$|\bin\s+cash\b|\bcash\b",
    re.IGNORECASE,
)
FINANCE_RE = re.compile(
    r"(?:/\s*(?:month|mo)\b|\bper\s+month\b|\bmonthly\b|\bmonthy\b|\bp\.?\s*m\.?\b|\binstallments?\b)",
    re.IGNORECASE,
)
NON_PRICE_RE = re.compile(
    r"\b(?:down\s*-?\s*payment|salary|deposit|fee|insurance|registration|evaluation|condition\s+report|vat|tax)\b",
    re.IGNORECASE,
)
NON_ODOMETER_RE = re.compile(
    r"\b(?:warranty|service|servicing|contract|plan|valid\s+till|until|up\s+to|driving\s+range|range|wltp|battery|single\s+charge|top\s+speed|maximum\s+speed|next\s+service|last\s+service)\b",
    re.IGNORECASE,
)
ODOMETER_MARKER_RE = re.compile(
    r"\b(?:mileage|odometer|driven|done|only|just)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class SourceFact:
    value: int
    evidence: str


def _number(raw: str) -> int | None:
    value = raw.replace(" ", "").replace(",", "")
    if re.fullmatch(r"\d+\.\d{3}", value):
        value = value.replace(".", "")
    try:
        parsed = float(value)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else None


def extract_cash_price(title: str, description: str) -> SourceFact | None:
    text = title + "\n" + description
    candidates: list[tuple[int, str, bool]] = []
    for match in MONEY_RE.finditer(text):
        value = _number(match.group("amount_after") or match.group("amount_before"))
        if value is None or not 10_000 <= value <= 10_000_000:
            continue
        before = text[max(0, match.start() - 45) : match.start()]
        after = text[match.end() : match.end() + 35]
        immediate_after = after[:15]
        separate_monthly_amount = bool(
            re.match(r"\s*monthly\s+installment\s+\d{2,4}", after, re.IGNORECASE)
        )
        if FINANCE_RE.search(immediate_after) and not separate_monthly_amount:
            continue
        if NON_PRICE_RE.search(before[-25:]) and not re.search(
            r"\bin\s+cash\b", after[:15], re.IGNORECASE
        ):
            continue
        if NON_PRICE_RE.search(immediate_after) and not re.search(
            r"\bin\s+cash\b", immediate_after, re.IGNORECASE
        ):
            continue
        marked = bool(
            PRICE_MARKER_RE.search(before[-35:])
            or re.match(r"\s*(?:in\s+cash|cash)\b", after, re.IGNORECASE)
        )
        cash_suffix = re.match(r"\s*in\s+cash\b", after, re.IGNORECASE)
        evidence = (
            " ".join((match.group() + cash_suffix.group()).split())
            if cash_suffix
            else " ".join((before[-25:] + match.group() + after[:18]).split())
        )
        candidates.append((value, evidence, marked))
    for match in AR_PRICE_RE.finditer(text):
        value = _number(match.group("number"))
        if value is not None and 10_000 <= value <= 10_000_000:
            candidates.append((value, match.group(), True))
    if not candidates:
        return None
    # A clearly marked cash/selling price wins; conflicting prices stay unknown.
    marked = {value for value, _, is_marked in candidates if is_marked}
    values = marked or {value for value, _, _ in candidates}
    if len(values) != 1:
        return None
    chosen = next(iter(values))
    evidence = next(item[1] for item in candidates if item[0] == chosen)
    return SourceFact(chosen, evidence)


def extract_mileage(title: str, description: str) -> SourceFact | None:
    text = title + "\n" + description
    candidates: list[tuple[int, str, bool]] = []
    excluded_values: set[int] = set()
    for match in DISTANCE_RE.finditer(text):
        value = _number(match.group("number"))
        if value is None or value > 2_000_000:
            continue
        before = text[max(0, match.start() - 65) : match.start()]
        after = text[match.end() : match.end() + 12]
        if re.match(r"\s*/\s*h\b|\s*per\s+hour\b", after, re.IGNORECASE) or re.search(
            r"(?:0\s*[-–]\s*)$", before
        ):
            excluded_values.add(value)
            continue
        marked = bool(
            ODOMETER_MARKER_RE.search(before[-28:])
            or re.search(r"\bmileage\b", after, re.IGNORECASE)
        )
        explicit_odometer = bool(
            re.search(
                r"\b(?:mileage|odometer|driven|done)\b", before[-28:], re.IGNORECASE
            )
            or re.search(r"\bmileage\b", after, re.IGNORECASE)
        )
        dealer_spec = bool(
            re.search(r"\bGCC Specs\b.{0,80}$", before, re.IGNORECASE | re.DOTALL)
            and not re.search(
                r"\b(?:last|next) service\b|\b(?:until|up to|valid till)\b",
                before[-55:],
                re.IGNORECASE,
            )
        )
        if NON_ODOMETER_RE.search(before[-55:]) and not (
            explicit_odometer or dealer_spec
        ):
            excluded_values.add(value)
            continue
        evidence = " ".join((before[-24:] + match.group() + after[:10]).split())
        candidates.append((value, evidence, marked))
    for match in AR_MILEAGE_RE.finditer(text):
        value = _number(match.group("number"))
        if value is not None and value <= 2_000_000:
            candidates.append((value, match.group(), True))
    candidates = [item for item in candidates if item[0] not in excluded_values]
    if not candidates:
        return None
    marked = {value for value, _, is_marked in candidates if is_marked}
    values = marked or {value for value, _, _ in candidates}
    if len(values) != 1:
        return None
    chosen = next(iter(values))
    evidence = next(item[1] for item in candidates if item[0] == chosen)
    return SourceFact(chosen, evidence)


def extract_vehicle_facts(title: str, description: str) -> dict[str, int | str | None]:
    price = extract_cash_price(title, description)
    mileage = extract_mileage(title, description)
    return {
        "price_aed": price.value if price else None,
        "price_evidence": price.evidence if price else None,
        "mileage_km": mileage.value if mileage else None,
        "mileage_evidence": mileage.evidence if mileage else None,
    }

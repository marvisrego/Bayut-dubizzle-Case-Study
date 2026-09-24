"""Deterministic scope, reference, and source-fact rules for chat."""

from __future__ import annotations

import re

from app.models.car import Car
from app.services.memory import SessionContext

ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}
ORDINAL_RE = re.compile(r"\b(first|1st|second|2nd|third|3rd)\b", re.IGNORECASE)
PRONOUN_RE = re.compile(
    r"\b(it|that one|this one|that car|this car|the vehicle)\b", re.IGNORECASE
)
CAR_ID_RE = re.compile(r"\bCAR_\d{4}\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s-]?)?(?:\d[\s()-]?){8,14}\d(?!\w)")
PREFERENCE_RE = re.compile(
    r"\b(?:i\s+(?:generally\s+|usually\s+|really\s+)?prefer|"
    r"i(?:'m|m|\s+am)\s+(?:really\s+)?(?:into|inot)|"
    r"i\s+(?:like|love)\s+(?!that\b|this\b|the\b|it\b)|"
    r"my\s+(?:favorite|favourite|preference|budget)|remember\s+that|"
    r"i(?:'m|\s+am)\s+looking\s+for|i\s+want\s+to\s+stick\s+with)\b",
    re.IGNORECASE,
)
SEARCH_RE = re.compile(
    r"\b(?:show\s+me|find\s+me|search\s+for|looking\s+for|want\s+to\s+see)\b",
    re.IGNORECASE,
)
LIKE_RE = re.compile(
    r"\b(?:i\s+(?:like|liked|love)\s+(?:that|this|the|it|CAR_\d{4})|save\s+(?:that|this|the|it|CAR_\d{4})|favorite\s+(?:that|this|the)|remember\s+(?:that|this)\s+car)\b",
    re.IGNORECASE,
)
NON_AED_RE = re.compile(
    r"(?:\$|\b(?:USD|EUR|GBP|INR|dollars?|euros?|pounds?)\b)", re.IGNORECASE
)
COMPETITOR_RE = re.compile(
    r"\b(?:carswitch|cars24|dubicars|yallamotor|autotrader|carvana|cargurus|"
    r"other\s+used.car\s+(?:platform|site|marketplace)|competing\s+(?:platform|site))\b",
    re.IGNORECASE,
)
UNRELATED_RE = re.compile(
    r"\b(?:write\s+(?:me\s+)?(?:code|(?:some\s+)?python\s+code|a\s+program|a\s+python\s+script)|"
    r"debug\s+(?:my\s+)?(?:code|python|javascript)|"
    r"how\s+to\s+code|programming|"
    r"who\s+was\s+(?:the\s+)?(?:president|king|emperor)|"
    r"history\s+of|world\s+war|capital\s+of)\b",
    re.IGNORECASE,
)


def is_out_of_scope(message: str) -> bool:
    return bool(COMPETITOR_RE.search(message) or UNRELATED_RE.search(message))


def resolve_reference(
    message: str, context: SessionContext
) -> tuple[str | None, str | None]:
    explicit = CAR_ID_RE.search(message)
    if explicit:
        return explicit.group().upper(), None
    ordinal = ORDINAL_RE.search(message)
    if ordinal:
        index = ORDINALS[ordinal.group().lower()]
        if index >= len(context.last_search_results):
            return (
                None,
                (
                    "I don't have that numbered car in this session. Please run a "
                    "search or choose a shown car."
                ),
            )
        return context.last_search_results[index], None
    if PRONOUN_RE.search(message):
        if context.selected_car_id:
            return context.selected_car_id, None
        if len(context.last_search_results) == 1:
            return context.last_search_results[0], None
        return (
            None,
            (
                "Which car do you mean? Please give its listing ID or its "
                "position in the results."
            ),
        )
    return None, None


def mentioned_text(value: str, message: str, prior: str | None = None) -> bool:
    normalized = value.casefold()
    haystack = message.casefold()
    if normalized in haystack or (prior is not None and normalized == prior.casefold()):
        return True
    prefix = normalized.split("-")[0].strip()
    return len(prefix) >= 4 and prefix in haystack


def amount_mentioned(amount: int, message: str) -> bool:
    normalized = re.sub(r"[,_\s]", "", message.casefold())
    if str(amount) in normalized:
        return True
    if amount >= 1000 and amount % 1000 == 0:
        return f"{amount // 1000}k" in normalized
    return False


def search_clause(message: str) -> str:
    search = SEARCH_RE.search(message)
    preference = PREFERENCE_RE.search(message)
    if search and preference and search.start() < preference.start():
        return message[search.end() : preference.start()]
    if search:
        return message[search.end() :]
    return (
        message[: preference.start()]
        if preference and preference.start() > 0
        else message
    )


def explicit_filters(message: str, makes: list[str], models: list[str]) -> dict:
    """Recognize user-stated hard constraints independently of the planner."""
    clause = search_clause(message)
    found: dict = {}
    for field, candidates in (("make", makes), ("model", models)):
        hits = [
            value
            for value in candidates
            if re.search(
                r"(?<!\w)" + re.escape(value) + r"s?(?!\w)", clause, re.IGNORECASE
            )
        ]
        if len(hits) == 1:
            found[field] = hits[0]
    if NON_AED_RE.search(message):
        return found
    amount = r"(\d{1,3}(?:,\d{3})+|\d+)(k)?"
    upper = re.search(
        r"\b(?:under|below|less\s+than|up\s+to|max(?:imum)?)\s*(?:aed\s*)?"
        + amount
        + r"\b",
        clause,
        re.IGNORECASE,
    )
    lower = re.search(
        r"\b(?:over|above|more\s+than|at\s+least|min(?:imum)?)\s*(?:aed\s*)?"
        + amount
        + r"\b",
        clause,
        re.IGNORECASE,
    )
    for match, key in ((upper, "max_price_aed"), (lower, "min_price_aed")):
        if match and not re.search(
            r"\b(?:km|mileage|kilometres?)\b",
            clause[max(0, match.start() - 12) : match.end() + 12],
            re.IGNORECASE,
        ):
            number = int(match.group(1).replace(",", "")) * (
                1000 if match.group(2) else 1
            )
            found[key] = number
    year = re.search(
        r"\b(19\d{2}|20\d{2})\s*(?:or\s+newer|and\s+newer|onwards|or\s+later)\b",
        clause,
        re.IGNORECASE,
    )
    if year:
        found["min_year"] = int(year.group(1))
    year = re.search(
        r"\b(?:before|older\s+than)\s+(19\d{2}|20\d{2})\b", clause, re.IGNORECASE
    )
    if year:
        found["max_year"] = int(year.group(1)) - 1
    return found


def allowed_preference_updates(message: str, updates: dict) -> dict:
    match = PREFERENCE_RE.search(message)
    if not match:
        return {}
    clause = re.split(
        r"[,.;]|\b(?:but|show\s+me|find\s+me)\b",
        message[match.end() :],
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].casefold()
    allowed: dict = {}
    for field, value in updates.items():
        if value is None:
            continue
        if field in (
            "preferred_makes",
            "preferred_models",
            "preferred_colors",
            "other_preferences",
        ):
            selected = [item for item in value if item.casefold() in clause]
            if selected:
                allowed[field] = selected
        elif field == "preferred_body_type":
            if value.casefold() in clause:
                allowed[field] = value
        elif field in ("budget_min_aed", "budget_max_aed"):
            if re.search(
                r"\bmy\s+budget\b|\bi\s+can\s+spend\b", message, re.IGNORECASE
            ) and amount_mentioned(value, message):
                allowed[field] = value
        elif field in ("min_year", "max_mileage_km"):
            if amount_mentioned(value, clause):
                allowed[field] = value
    return allowed


def requested_attribute(message: str, hinted: str | None = None) -> str:
    for word, attribute in (
        ("mileage", "mileage"),
        ("kilometer", "mileage"),
        ("kilometre", "mileage"),
        ("price", "price"),
        ("cost", "price"),
        ("budget", "price"),
        ("warranty", "warranty"),
        ("colour", "color"),
        ("color", "color"),
        ("year", "year"),
    ):
        if word in message.casefold():
            return attribute
    if re.search(
        r"\b(?:does\s+(?:it|this|that)\s+have|has\s+it\s+got|is\s+there)\b",
        message,
        re.IGNORECASE,
    ):
        return "feature"
    return (
        hinted
        if hinted in {"mileage", "price", "warranty", "color", "year", "description"}
        else "description"
    )


def factual_detail(car: Car, attribute: str) -> str:
    prefix = f"{car.listing_id} ({car.year} {car.make} {car.model} {car.trim})"
    if attribute == "mileage":
        return (
            f"{prefix}: mileage is {car.mileage_km:,} km."
            if car.mileage_km is not None
            else f"{prefix}: verified mileage is not listed."
        )
    if attribute == "price":
        return (
            f"{prefix}: the listed cash price is AED {car.price_aed:,}."
            if car.price_aed is not None
            else f"{prefix}: a cash price is not listed."
        )
    if attribute == "year":
        return f"{prefix}: the listed year is {car.year}."
    if attribute in ("warranty", "color"):
        # No verified structured field currently exists for either attribute.
        return f"{prefix}: {attribute} is not listed as a verified vehicle detail."
    if attribute == "feature":
        return f"{prefix}: that feature is not specified as a verified vehicle detail."
    return (
        f"{prefix}. A cash price is "
        + (f"AED {car.price_aed:,}" if car.price_aed is not None else "not listed")
        + "; verified mileage is "
        + (f"{car.mileage_km:,} km" if car.mileage_km is not None else "not listed")
        + "."
    )


def factual_answer(car: Car, message: str, hinted: str | None = None) -> str:
    lower = message.casefold()
    if re.search(r"\b(?:price|cost)\b", lower) and re.search(
        r"\b(?:mileage|kilometres?|kilometers?|km)\b", lower
    ):
        price = f"AED {car.price_aed:,}" if car.price_aed is not None else "not listed"
        mileage = (
            f"{car.mileage_km:,} km" if car.mileage_km is not None else "not listed"
        )
        return (
            f"{car.listing_id} ({car.year} {car.make} {car.model} {car.trim}): "
            f"listed cash price is {price}; mileage is {mileage}."
        )
    return factual_detail(car, requested_attribute(message, hinted))

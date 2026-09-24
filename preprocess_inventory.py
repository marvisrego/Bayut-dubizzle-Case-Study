"""Prepare the supplied cleaned worksheet for grounded inventory retrieval.

Run: python preprocess_inventory.py
Requires: openpyxl (``python -m pip install openpyxl``).

The source workbook is never modified. Empty CSV cells represent unknown values,
not estimates. ``description_raw`` is copied verbatim from the workbook.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from openpyxl import load_workbook

SOURCE = Path(__file__).with_name("Cars_data.xlsx")
OUTPUT = Path(__file__).with_name("data") / "inventory_enriched.csv"
SHEET = "cleaned dataset"

OUTPUT_COLUMNS = (
    "Listing_ID",
    "year",
    "make",
    "model",
    "trim",
    "title",
    "description_raw",
    "price_aed",
    "color",
    "body_type",
    "mileage_km",
    "language",
    "photo_url",
)

MAKE_ALIASES = {"mitsubshi": "mitsubishi", "mitubshi": "mitsubishi"}
COLORS = {
    "white": "white",
    "black": "black",
    "silver": "silver",
    "gray": "gray",
    "grey": "gray",
    "red": "red",
    "blue": "blue",
    "yellow": "yellow",
    "gold": "gold",
    "green": "green",
    "orange": "orange",
    "brown": "brown",
    "beige": "beige",
    "purple": "purple",
    "أبيض": "white",
    "ابيض": "white",
    "أسود": "black",
    "اسود": "black",
    "أحمر": "red",
    "احمر": "red",
    "أزرق": "blue",
    "ازرق": "blue",
}
COLOR_WORDS = "|".join(sorted(map(re.escape, COLORS), key=len, reverse=True))
COLOR_RE = re.compile(rf"(?<!\w)({COLOR_WORDS})(?!\w)", re.IGNORECASE)

# Only models with a stable body style are included. Variant words in the title
# take precedence for models sold in multiple body styles.
BODY_TYPE_BY_MODEL = {
    **dict.fromkeys(
        (
            "explorer",
            "range rover velar",
            "g-class brabus",
            "g-class",
            "cayenne",
            "bentayga",
            "cullinan",
            "pajero sport",
            "pajero",
            "x1",
            "x6",
            "mkx",
            "dbx",
            "x-trail",
            "aviator",
            "glc coupe",
            "tucson",
            "f-pace",
            "gls-class",
            "xterra",
            "h3",
            "range rover sport",
            "levante",
            "x7",
            "countryman",
            "q7",
            "grandland x",
            "patrol safari",
            "lx-series",
            "glk-class",
            "wrangler",
            "highlander",
            "lr4",
            "land cruiser",
            "sportage",
            "rav 4",
            "xc60",
        ),
        "suv",
    ),
    **dict.fromkeys(
        (
            "altima",
            "q50",
            "xe",
            "ghibli",
            "ghost",
            "camry",
            "versa",
            "3-series",
            "s-class",
            "g90",
        ),
        "sedan",
    ),
    **dict.fromkeys(("wraith", "challenger", "camaro", "brooklands"), "coupe"),
    **dict.fromkeys(("dawn", "sf90 spider"), "convertible"),
    **dict.fromkeys(("golf", "megane", "beetle"), "hatchback"),
    "landtrek": "pickup",
    "hiace": "van",
}

MONEY_RE = re.compile(
    r"(?<!\w)(?:(?:AED|DHS?\.?|DIRHAMS?)\s*[:\-]?\s*(?P<prefix>\d[\d,]*(?:\.\d{1,2})?)"
    r"|(?P<suffix>\d[\d,]*(?:\.\d{1,2})?)\s*(?:AED|DHS?\.?|DIRHAMS?))(?!\w)",
    re.IGNORECASE,
)
MONTHLY_AFTER_RE = re.compile(
    r"^\s*(?:/|-)?\s*(?:per\s+)?(?:mo\b|month\w*\b|pm\b)", re.IGNORECASE
)
MONEY_EXPENSE_RE = re.compile(
    r"\b(?:salary|insurance|evaluation|registration|processing\s+fee|"
    r"deposit|down[ -]?payment)\b",
    re.IGNORECASE,
)
MILEAGE_RE = re.compile(
    r"(?<!\d)(\d{1,3}(?:[ ,]\d{3})+|\d+)\s*\(?\s*"
    r"(?:km|kms|kilometres|kilometers)\s*\)?\b",
    re.IGNORECASE,
)
ODOMETER_RE = re.compile(
    r"\b(?:mileage|odometer)\s*[:\-]?\s*(?:just\s*)?(\d{1,3}(?:[ ,]\d{3})+|\d+)"
    r"\s*\(?\s*(?:km|kms|kilometres|kilometers)?\s*\)?\b",
    re.IGNORECASE,
)
ARABIC_RE = re.compile(r"[\u0621-\u064A]")
LATIN_RE = re.compile(r"[A-Za-z]")


def normalize_category(value: object, *, make: bool = False) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    normalized = " ".join(str(value or "").casefold().split())
    return MAKE_ALIASES.get(normalized, normalized) if make else normalized


def extract_price_aed(title: str, description: str) -> int | None:
    """Accept one-off AED amounts; reject installments and incidental fees."""
    candidates: list[tuple[int, int]] = []
    for source, text in (("title", title), ("description", description)):
        for match in MONEY_RE.finditer(text):
            raw_amount = (match.group("prefix") or match.group("suffix")).replace(
                ",", ""
            )
            try:
                amount = Decimal(raw_amount)
            except InvalidOperation:
                continue
            if (
                amount != amount.to_integral_value()
                or not 5_000 <= amount <= 20_000_000
            ):
                continue
            before = text[max(0, match.start() - 42) : match.start()]
            after = text[match.end() : match.end() + 32]
            cash = bool(re.match(r"^\s*(?:in\s+)?cash\b", after, re.IGNORECASE))
            if MONTHLY_AFTER_RE.match(after):
                continue
            if not cash and (
                MONEY_EXPENSE_RE.search(before[-26:])
                or MONEY_EXPENSE_RE.search(after[:22])
            ):
                continue
            price_label = bool(
                re.search(r"\b(?:price|payment|reduced)\b", before[-30:], re.IGNORECASE)
            )
            score = (
                (100 if cash else 0)
                + (40 if price_label else 0)
                + (10 if source == "title" else 0)
            )
            candidates.append((score, int(amount)))
    return max(candidates, default=(0, None))[1]


def extract_color(title: str, description: str) -> str | None:
    def first_color(text: str) -> str | None:
        match = COLOR_RE.search(text)
        return COLORS[match.group(1).casefold()] if match else None

    # A badge or trim name is not necessarily the paint color.
    title_without_badges = re.sub(r"\bblack\s+badge\b", "", title, flags=re.IGNORECASE)
    color = first_color(title_without_badges)
    if color:
        return color
    for pattern in (
        rf"\bexterior\s*(?:paint\s+)?(?:colou?r\s*)?[:\-]?\s*(?:diamond\s+)?({COLOR_WORDS})\b",
        rf"\bcolou?r\s*[:\-]?\s*({COLOR_WORDS})\b",
        rf"\b({COLOR_WORDS})\s+colou?r\b",
    ):
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return COLORS[match.group(1).casefold()]
    return None


def extract_body_type(
    model: str, trim: str, title: str, description: str
) -> str | None:
    heading = f"{model} {trim} {title}".casefold()
    if re.search(r"\b(convertible|roadster|spider|drophead|cabriolet)\b", heading):
        return "convertible"
    if re.search(r"\b(pick[ -]?up|truck)\b", heading):
        return "pickup"
    if re.search(r"\b(station(?:\s+wagon)?|wagon|estate)\b", heading):
        return "wagon"
    if model == "continental":
        if re.search(r"\b(gtc|convertible)\b", heading):
            return "convertible"
        if re.search(r"\b(flying\s*spur)\b", heading):
            return "sedan"
        if re.search(r"\bgt\b", heading):
            return "coupe"
        return None
    if model == "flying spur":
        return "sedan"
    if model == "phantom" and "drophead" not in heading:
        return "sedan"
    if model == "genesis" and re.search(r"\bg80\b", heading):
        return "sedan"
    if model in BODY_TYPE_BY_MODEL:
        return BODY_TYPE_BY_MODEL[model]
    for pattern, body in (
        (r"\bsuv\b", "suv"),
        (r"\bvan\b", "van"),
        (r"\bcoupe\b", "coupe"),
        (r"\bsedan\b", "sedan"),
        (r"\bhatchback\b", "hatchback"),
    ):
        if re.search(pattern, title, re.IGNORECASE):
            return body
    # Only use an explicitly labelled body style in the description. Dealer
    # paragraphs often mention unrelated cars and should not drive inference.
    match = re.search(
        r"\bbody\s+(?:type|style)\s*[:\-]\s*(suv|sedan|coupe|convertible|hatchback|pickup|van|wagon)\b",
        description,
        re.IGNORECASE,
    )
    return match.group(1).casefold() if match else None


def extract_mileage_km(title: str, description: str) -> int | None:
    candidates: list[tuple[int, int]] = []
    for source, text in (("title", title), ("description", description)):
        for regex, base_score in ((ODOMETER_RE, 20), (MILEAGE_RE, 0)):
            for match in regex.finditer(text):
                value = float(match.group(1).replace(",", "").replace(" ", ""))
                if not value.is_integer() or not 0 <= value <= 1_000_000:
                    continue
                before = text[max(0, match.start() - 35) : match.start()].casefold()
                after = text[match.end() : match.end() + 15].casefold()
                if re.search(
                    r"(?:warranty|service|until|up to|up-to|every)\W{0,15}$", before
                ):
                    continue
                if re.match(r"^\s*/\s*h\b", after):
                    continue
                score = base_score + (10 if source == "title" else 0)
                candidates.append((score, int(value)))
    return max(candidates, default=(0, None))[1]


def detect_language(title: str, description: str) -> str:
    combined = title + " " + description
    arabic = len(ARABIC_RE.findall(combined))
    latin = len(LATIN_RE.findall(combined))
    if not arabic:
        return "en"
    # Model names such as "S" or "LR4" do not turn an Arabic listing into a
    # substantively bilingual description.
    return "ar" if arabic / (arabic + latin) >= 0.8 else "mixed"


def load_inventory(path: Path) -> list[dict[str, object]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[SHEET]
        rows = sheet.values
        headers = list(next(rows))
        required = {
            "Listing_ID",
            "year",
            "make",
            "model",
            "trim",
            "title",
            "description",
            "photo_url",
        }
        if not required.issubset(headers):
            raise ValueError(
                f"Missing worksheet columns: {sorted(required - set(headers))}"
            )
        records = []
        seen_ids: set[int] = set()
        for cells in rows:
            row = dict(zip(headers, cells))
            if not any(value is not None for value in row.values()):
                continue  # The workbook contains many formatted, empty rows.
            listing_id = int(row["Listing_ID"])
            if listing_id in seen_ids:
                raise ValueError(f"Duplicate Listing_ID: {listing_id}")
            seen_ids.add(listing_id)
            title = str(row["title"] or "")
            description = str(row["description"] or "")
            photo_url = str(row["photo_url"] or "")
            parsed_url = urlsplit(photo_url)
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                raise ValueError(f"Invalid photo_url on Listing_ID {listing_id}")
            model = normalize_category(row["model"])
            trim = normalize_category(row["trim"])
            records.append(
                {
                    "Listing_ID": listing_id,
                    "year": int(row["year"]),
                    "make": normalize_category(row["make"], make=True),
                    "model": model,
                    "trim": trim,
                    "title": title,
                    "description_raw": description,
                    "price_aed": extract_price_aed(title, description),
                    "color": extract_color(title, description),
                    "body_type": extract_body_type(model, trim, title, description),
                    "mileage_km": extract_mileage_km(title, description),
                    "language": detect_language(title, description),
                    "photo_url": photo_url,
                }
            )
        return records
    finally:
        workbook.close()


def write_csv(records: list[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    records = load_inventory(args.input)
    write_csv(records, args.output)
    print(f"Wrote {len(records)} listings to {args.output}")
    for field in ("price_aed", "color", "body_type", "mileage_km"):
        print(
            f"{field}: {sum(row[field] is not None for row in records)}"
            f"/{len(records)} populated"
        )
    print("language:", dict(Counter(str(row["language"]) for row in records)))


if __name__ == "__main__":
    main()

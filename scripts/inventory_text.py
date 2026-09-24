"""Deterministic text cleaning for car embeddings; source text is never changed."""

from __future__ import annotations

import re

URL_RE = re.compile(
    r"(?i)(?:https?://|www\.)[^\s<>()]+|"
    r"\b[a-z0-9.-]+\.(?:com|ae|net|org|co|io)\b[^\s<>()]*"
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:\+?971|00971)(?:[\s().-]*\d){8,9}|"
    r"0[24567](?:[\s().-]*\d){7,8})(?!\d)"
)
HASHTAG_RE = re.compile(r"(?<!\w)#[\w-]+", re.UNICODE)
HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z][A-Za-z0-9_.]+")
CONTACT_RE = re.compile(
    r"(?i)\b(?:whats?app|contact\s+us|call|call/whatsapp|"
    r"phone\s*(?:no|number)?|telephone|mobile\s*(?:no|number)?|"
    r"for\s+calling|for\s+whatsapp)\b|(?:اتصل|تواصل|واتساب)"
)
SOCIAL_RE = re.compile(
    r"(?i)\b(?:instagram|facebook|twitter|tiktok|linkedin|youtube|"
    r"pinterest|snapchat|social\s+media|follow\s+us|insta)\b|تابعونا"
)
ADDRESS_RE = re.compile(
    r"(?i)\b(?:address|showroom|p\.?\s*o\.?\s*box|location\s*[:#]|"
    r"al\s+quoz|ras\s+al\s+khor|al\s+aweer|souq\s+al\s+haraj|"
    r"ducamz|auto\s+market|industrial\s+area|sheikh\s+zayed\s+road|"
    r"office|location)\b|(?:العنوان|موقعنا)"
)
HOURS_RE = re.compile(
    r"(?i)\b(?:opening\s+hours|working\s+hours|open\s+7\s+days|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
    r"(?:ساعات\s+العمل|السبت|الجمعة|الساعه)"
)
BOILERPLATE_START_RE = re.compile(
    r"(?i)\b(?:about\s+us|follow\s+us|contact\s+us|call/whatsapp|"
    r"visit\s+our\s+showroom|why\s+choose\s+us|our\s+services?|"
    r"what\s+is\s+dubizzle\s+cars|what\s+to\s+expect\s+from\s+dubizzle|"
    r"check\s+out\s+our\s+website|to\s+find\s+out\s+more|"
    r"for\s+more\s+details|for\s+more\s+information(?:\s+and\s+details)?|"
    r"service\s+we\s+provide|"
    r"you\s+can\s+also\s+stay\s+connected|"
    r"we\s+welcome\s+you\s+to\s+visit|available\s+(?:now\s+)?at\s+"
    r"(?:[A-Z][a-z]+\s+){1,3}(?:Auto|Motors|Cars))\b"
)
GENERIC_RE = re.compile(
    r"(?i)\b(?:a\s+decade\s+of\s+experience|we\s+believe\s+the\s+process|"
    r"this\s+service\s+is\s+provided|buy\s+this\s+car\s+with\s+confidence|"
    r"we\s+manage\s+the\s+interaction|your\s+funds\s+are\s+fully\s+protected|"
    r"we\s+are\s+an\s+iso|iso\s+9001\s+certified|"
    r"best\s+deals\s+by\s+country|excellent\s+customer\s+service|"
    r"over\s+1500\s+vehicles|we\s+have\s+direct\s+access\s+more\s+than|"
    r"we\s+have\s+direct\s+access\s+more\s+then|"
    r"a\s+name\s+you\s+can\s+trust|welcome\s+to\s+mirza|"
    r"best\s+part\?|no\s+guesswork|no\s+stress|"
    r"don't\s+miss\s+out|book\s+a\s+test\s+drive\s+today|"
    r"terms\s*(?:and|&)\s*conditions\s+apply|t\s*&\s*cs\s+apply|"
    r"know\s+what\s+you're\s+buying|all\s+cars\s+undergo|"
    r"need\s+a\s+more\s+comprehensive\s+inspection|"
    r"upgrade\s+to\s+the\s+advanced\s+condition\s+report|"
    r"looking\s+to\s+finance|ask\s+us|"
    r"luxurious\s+automot(?:ive|ative)\s+wholesaler|"
    r"specialized\s+in\s+new\s+and\s+pre-owned|"
    r"buy,\s*sell,\s*and\s*trade|"
    r"after\s+sales\s+service|registration\s+assistance|"
    r"dedicated\s+team\s+support|from\s+unique\s+to\s+trendy|"
    r"interactive\s+updates\s+of\s+process|"
    r"mr\.?\s+[a-z]+|"
    r"insurance\s+options|export\s+deals|"
    r"expert\s+sales\s+and\s+after-sales\s+support|"
    r"we\s+can\s+deliver\s+the\s+car|"
    r"trusted\s+cars\s+dealership|customer\s+first|"
    r"selling\s+your\s+car\s+to\s+us|"
    r"we\s+do\s+bank\s+finance|"
    r"feel\s+free\s+to|"
    r"summer\s+offer|free\s+registration|free\s+window\s+tinting|"
    r"free\s+salik\s+tag|"
    r"we\s+offer\s+this\s+exceptional|"
    r"flexible\s+bank\s+financing|"
    r"the\s+most\s+competitive\s+price|"
    r"this\s+\d{4}\s+\w+.*\s+is\s+a\s+real\s+head-turner|"
    r"as\s+this\s+will\s+not\s+be\s+available|"
    r"we\s+help\s+sellers\s+find|"
    r"relax\s+as\s+the\s+experts|"
    r"we\s+can\s+buy\s+any\s+type|"
    r"are\s+you\s+looking\s+to\s+sell|"
    r"selling\s+your\s+car|"
    r"please\s+don.t\s+hesitate|"
    r"one\s+of\s+the\s+oldest\s+auto\s+dealers|"
    r"experience\s+in\s+shipping\s+worldwide|"
    r"known\s+for\s+the\s+best\s+price|"
    r"flexible\s+buying\s+options|"
    r"since\s+\d{4}\b|"
    r"we\s+are\s+open|"
    r"deals\s+with\s+gcc\s+cars\s+only|"
    r"perfect\s+for\s+buyers\s+searching|"
    r"elevate\s+your\s+adventures|"
    r"feel\s+free\s+to|"
    r"every\s+model\s+for\s+sale\s+has\s+been|"
    r"why\s+choose\s+[a-z ]+\s+cars|"
    r"experience\s+the\s+perfect\s+blend|"
    r"detailing\s*&\s*car\s+care|"
    r"car\s+registration\s+assistance|"
    r"please\s+don't\s+hesitate|"
    r"we\s+are\s+open|"
    r"we\s+welcome\s+you|"
    r"please\s+book\s+an\s+appointment|price\s+is\s+negotiable|"
    r"come\s+visit\s+us|"
    r"do\s+not\s+hesitate\s+to)\b"
)
FINANCE_RE = re.compile(
    r"(?i)\b(?:monthly|per\s+month|down\s*-?\s*payment|"
    r"downpayment|bank\s+finance|bank\s+terms|bank\s+financing|"
    r"installments?|payable\s+in|finance\s+also|"
    r"financing\s+options|trade[- ]?in\s+option)\b|"
    r"(?i:\bp\.?m\.?\b|/\s*month\b|\b\d[\d,]*\s*pm\b)"
)
DEALER_RE = re.compile(
    r"(?i)\b(?:motors|cars\s+fze|automobile\s+fze|auto\s+trading|"
    r"cars\s+trading|car\s+showroom|car\s+dealership|wholesaler)\b"
)
PROMO_RE = re.compile(
    r"(?i)\b(?:best\s+rr\s+sport|frankly\s+this\s+is\s+the\s+best|"
    r"top\s+of\s+the\s+options|perfect\s+blend\s+of\s+luxury|"
    r"discover\s+the\s+exceptional|"
    r"best\s+part\?|dream\s+car|best\s+part\s+about\s+the\s+car|"
    r"honestly\s+we\s+can\s+say|cleanest\s+\w+|"
    r"the\s+aforementioned\s+price\s+is\s+exclusive)\b"
)
REFERENCE_RE = re.compile(r"(?i)\b(?:reference\s+number|ref\s*#\s*\d+)\b")
FOOTER_START_RE = re.compile(
    r"(?i)\b(?:about\s+us\s*:|follow\s+us\s+on|"
    r"our\s+services?\s*:|what\s+is\s+dubizzle\s+cars\?|"
    r"why\s+choose\s+[A-Za-z ]+\s+cars\?)"
)
SHORT_NOISE = {
    "please",
    "our",
    "sales",
    "office",
    "mr",
    "mr.",
    "mrs",
    "mrs.",
    "rasheed",
    "flexible",
    "best part",
    "why choose",
    "payment plans through",
}
VEHICLE_DETAIL_RE = re.compile(
    r"(?i)\b(?:km|kms|mileage|warranty|service\s+contract|"
    r"service\s+history|specs?|gcc|japanese?|american|"
    r"engine|transmission|hp|bhp|accident|interior|exterior|"
    r"color|colour|sunroof|camera|turbo|cyl|price)\b"
)
VEHICLE_CUE_RE = re.compile(
    r"(?i)(?:\d[\d,. ]*\s*(?:km|kms)\b)|\b(?:model|trim|edition|year|"
    r"km|kms|mileage|odometer|"
    r"warranty|service\s+(?:history|contract|plan)|serviced|"
    r"accident|condition|paint|specs?|gcc|japan(?:ese)?|american|"
    r"engine|motor|transmission|automatic|manual|gear(?:box|s)?|"
    r"hp|bhp|torque|cyl(?:inder)?s?|cc|liter|litre|turbo|"
    r"petrol|diesel|hybrid|electric|battery|drivetrain|4wd|awd|"
    r"wheel|tyre|tire|rim|brake|suspension|"
    r"interior|exterior|color|colour|black|white|silver|beige|"
    r"red|blue|brown|grey|gray|yellow|leather|seat|"
    r"sunroof|panoramic|camera|sensor|radar|navigation|"
    r"carplay|bluetooth|audio|speaker|sound|"
    r"cruise|keyless|parking|safety|airbag|"
    r"door|roof|lights?|headlights?|tailgate|"
    r"original\s+keys?|owner|options?|features?|"
    r"price|aed|dirham|cash|"
    r"coupe|sedan|suv|convertible|hatchback|"
    r"clean\s+title|full\s+service|"
    r"rwd|fwd|v6|v8|v12)\b|"
    r"(?:السيارة|سيارة|موديل|كم|ضمان|صيانة|حالة|"
    r"نظيف|خالي|خالية|فتحة|سقف|كاميرا|جلد|مقاعد|"
    r"محرك|قير|دفع|رنجات|مواصفات|فل|صبغ|حوادث|"
    r"ممشى|عداد|سعر|درهم|بنزين|ديزل|بانوراما|لون)"
)
ARABIC_PROMO_RE = re.compile(
    r"(?:تسهيلات\s+(?:تسجيل|اقساط)|جميع\s+البنوك|"
    r"شراء\s+و\s+استبدال|جميع\s+انواع\s+السيارت|"
    r"السعر\s+قابل\s+للتفاوض|قابلية\s+الاقساط|"
    r"تمويل\s+عن\s+طريق|(?:امكانية|امكانيه)\s+تمويل|يوجد\s+لدينا|"
    r"الى\s+جميع\s+انحاء\s+العالم|يرجى\s+الاتصال)"
)
CITY_ONLY_RE = re.compile(r"(?i)^(?:dubai|abu\s+dhabi|sharjah)$")
GENERIC_HEADINGS = {
    "description",
    "summary",
    "highlights",
    "key details",
    "vehicle specs",
    "options & features",
    "features",
    "contact",
    "contact us",
    "about us",
    "our services",
    "our service",
    "equipment",
    "best part",
    "best part?",
    "why this car?",
    "flexible bank financing options",
}
DECORATIVE_RE = re.compile(r"^[\W_]{4,}$", re.UNICODE)
SEPARATOR_RE = re.compile(r"[-_=━—▔]{5,}")
BULLET_RE = re.compile(r"\s*[•●▪✅🔹]\s*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Za-z\u0600-\u06FF])")


def strip_links_and_contacts(value: str) -> str:
    value = URL_RE.sub(" ", value)
    value = EMAIL_RE.sub(" ", value)
    value = PHONE_RE.sub(" ", value)
    value = HANDLE_RE.sub(" ", value)
    return HASHTAG_RE.sub(" ", value)


def repeat_key(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def clean_unit(value: str) -> str:
    """Keep source-backed vehicle details and discard known ad/contact fragments."""
    value = value.strip()
    if not value or DECORATIVE_RE.fullmatch(value):
        return ""
    value = value.replace("_", " ")
    if value.casefold().strip(" :.-_?") in GENERIC_HEADINGS:
        return ""
    arabic_promo = ARABIC_PROMO_RE.search(value)
    if arabic_promo:
        value = value[: arabic_promo.start()] if arabic_promo.start() else ""
    value = re.sub(r"^\s*\d{1,2}\.\s+(?=\w)", "", value)
    if re.match(r"(?i)^why\s+this\b.*\?$|^.+\bhighlights\s*$", value):
        return ""
    value = re.sub(r"(?i)^\s*\d+\s+year\s+free\s+insurance\s*\([^)]*\)\s*", "", value)
    value = re.sub(r"(?i)^\s*best\s+[^-\n]{3,90}\s+-\s+", "", value)
    value = re.sub(
        r"(?i)\bcar\s+file\s+is\s+open\s+in\s+the\s+dealer\s*&\s+", "", value
    )
    finance = FINANCE_RE.search(value)
    if finance:
        prefix = value[: finance.start()].strip(" |;:,-–—•*.")
        if len(prefix) < 25 or not VEHICLE_DETAIL_RE.search(prefix):
            return ""
        value = prefix
    value = re.sub(r"(?i)\bsummer\s*offer\b", " ", value)
    matches = [
        match
        for pattern in (
            BOILERPLATE_START_RE,
            GENERIC_RE,
            SOCIAL_RE,
            HOURS_RE,
            ADDRESS_RE,
            PROMO_RE,
            REFERENCE_RE,
        )
        if (match := pattern.search(value))
    ]
    if matches:
        value = value[: min(match.start() for match in matches)]
    contact = CONTACT_RE.search(value)
    if contact:
        if re.search(r"[\u0600-\u06ff]", value):
            value = CONTACT_RE.sub(" ", value)
        else:
            value = value[: contact.start()]
    value = strip_links_and_contacts(value)
    value = re.sub(r"(?:📞|☎️|📍)", " ", value)
    value = " ".join(value.split()).strip(" |;:,-–—•*.")
    if value.casefold().strip(" :.-_?!") in SHORT_NOISE:
        return ""
    if CITY_ONLY_RE.fullmatch(value):
        return ""
    if re.fullmatch(r"\d+", value):
        return ""
    if DEALER_RE.search(value) and not re.search(
        r"(?i)\b(?:\d{4}|km|kms|mileage|warranty|specs?|gcc|japan|"
        r"engine|hp|bhp|color|colour|interior|exterior|service\s+history|"
        r"accident|sunroof|camera|transmission|aed)\b",
        value,
    ):
        return ""
    return value if re.search(r"\w", value, re.UNICODE) else ""


def make_embedding_text(row: dict) -> str:
    structured = " ".join(
        str(row[field])
        for field in ("year", "make", "model", "trim")
        if row[field] is not None
    )
    title_source = re.sub(r"(?i)\(car\s+by\s+[^)]+\)", " ", row["title_clean"] or "")
    title_segments = [clean_unit(segment) for segment in title_source.split("|")]
    title = " | ".join(segment for segment in title_segments if segment)
    if (
        re.search(r"(?i)\b(?:showroom|dealer|cars\s+trading)\b|معرض", title)
        and (row["model"] or "").casefold() not in title.casefold()
    ):
        title = ""
    description = row["description_clean"] or ""
    footer = FOOTER_START_RE.search(description)
    if footer and footer.start() > 40:
        description = description[: footer.start()]
    description = strip_links_and_contacts(description)
    description = re.sub(r"\bMr\.\s+", "Mr ", description)
    description = SEPARATOR_RE.sub("\n", description)
    description = BULLET_RE.sub("\n", description)
    parts = [structured]
    structured_key = repeat_key(structured)
    seen = {structured_key}
    title_key = repeat_key(title)
    if title and title_key not in seen:
        parts.append(title)
        seen.add(title_key)
    for raw_unit in description.splitlines():
        for sentence in SENTENCE_RE.split(raw_unit):
            unit = clean_unit(sentence)
            if not unit:
                continue
            if title and unit.casefold().startswith(title.casefold()):
                unit = unit[len(title) :].strip(" |;:,-–—•*")
            signature = repeat_key(unit)
            if (
                signature
                and signature not in seen
                and VEHICLE_CUE_RE.search(unit)
                and not (
                    len(signature) >= 8
                    and (signature in structured_key or signature in title_key)
                )
            ):
                seen.add(signature)
                parts.append(unit)
    return ". ".join(part for part in parts if part)


def has_noise(value: str) -> bool:
    return bool(
        URL_RE.search(value)
        or EMAIL_RE.search(value)
        or PHONE_RE.search(value)
        or CONTACT_RE.search(value)
        or SOCIAL_RE.search(value)
    )

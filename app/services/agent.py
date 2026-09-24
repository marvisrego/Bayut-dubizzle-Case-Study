"""NVIDIA tool planner with deterministic execution and grounded responses."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.schemas.agent import LeadUpdate, PreferenceUpdate
from app.schemas.api import ChatRequest, ChatResponse
from app.schemas.cars import CarResponse, SearchFilters
from app.services.agent_policy import (
    EMAIL_RE,
    LIKE_RE,
    NON_AED_RE,
    PHONE_RE,
    SEARCH_RE,
    allowed_preference_updates,
    amount_mentioned,
    explicit_filters,
    factual_answer,
    is_out_of_scope,
    mentioned_text,
    resolve_reference,
    search_clause,
)
from app.services.agent_tools import AgentTools
from app.services.booking import BookingError
from app.services.nvidia_chat import NvidiaChatClient, ToolCall

SYSTEM = (
    "You are the dubizzle cars assistant. Select provided tools for the user's "
    "request. Never invent inventory facts, prices, mileage, warranty, features, "
    "or availability. "
    "Search filters are temporary; save only explicitly ongoing preferences. "
    "Resolve follow-ups with session state. Collect date and time for bookings, "
    "which Python validates. Capture stated lead requirements naturally. Use "
    "decline_out_of_scope for unrelated tasks or competing platforms."
)
BOOKING_RE = re.compile(
    r"\b(?:book|booking|view|viewing|test.drive|schedule|appointment)\b", re.IGNORECASE
)
LIKED_MEMORY_RE = re.compile(
    r"\b(?:what|which)\b.*\b(?:like|liked|favo[u]?rite|favo[u]?rites)\b", re.IGNORECASE
)
PREFERENCE_MEMORY_RE = re.compile(
    r"\b(?:what|which)\b.*\b(?:prefer|preference|preferences)\b", re.IGNORECASE
)
GENERAL_MEMORY_RE = re.compile(
    r"\b(?:remember|remind me|looking for before|previously)\b", re.IGNORECASE
)


def _tool(
    name: str, description: str, properties: dict, required: list[str] | None = None
) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOLS = [
    _tool(
        "search_inventory",
        "Search inventory using user-stated filters and optional semantic needs.",
        {
            "filters": {
                "type": "object",
                "properties": {
                    k: {
                        "type": "string"
                        if k in {"make", "model", "trim", "source"}
                        else "integer"
                    }
                    for k in SearchFilters.model_fields
                },
            },
            "semantic_query": {"type": "string"},
            "top_k": {"type": "integer"},
        },
    ),
    _tool(
        "get_car_details",
        "Get a referenced car and requested attribute.",
        {"listing_id": {"type": "string"}, "attribute": {"type": "string"}},
        ["listing_id"],
    ),
    _tool("get_user_memory", "Recall preferences and liked cars.", {}),
    _tool(
        "update_user_preferences",
        "Save explicitly ongoing preferences.",
        {"updates": PreferenceUpdate.model_json_schema()},
        ["updates"],
    ),
    _tool(
        "remember_liked_car",
        "Remember an explicitly liked car.",
        {"listing_id": {"type": "string"}},
        ["listing_id"],
    ),
    _tool(
        "create_booking",
        "Request a viewing or test drive.",
        {
            "listing_id": {"type": "string"},
            "proposed_at": {
                "type": "string",
                "description": "ISO date and time in Dubai local time or with offset",
            },
        },
        ["listing_id", "proposed_at"],
    ),
    _tool(
        "save_lead",
        "Store stated requirements or contact.",
        {"update": LeadUpdate.model_json_schema()},
        ["update"],
    ),
    _tool("get_session_context", "Inspect previous results and selection.", {}),
    _tool("greet", "Respond to a greeting.", {}),
    _tool(
        "decline_out_of_scope",
        "Decline an unrelated request or competing used-car platform discussion.",
        {},
    ),
]


class SessionOwnershipError(PermissionError):
    pass


class ChatAgent:
    def __init__(self, tools: AgentTools, model: NvidiaChatClient):
        self.tools = tools
        self.model = model

    def _messages(self, context, profile, message: str) -> list[dict]:
        state = {
            "last_search_results": context.last_search_results[:10],
            "selected_car_id": context.selected_car_id,
            "active_filters": context.active_filters,
        }
        return [
            {"role": "system", "content": SYSTEM},
            {
                "role": "system",
                "content": "Long-term profile: "
                + json.dumps(asdict(profile) if profile else {}, ensure_ascii=False),
            },
            {
                "role": "system",
                "content": "Session state: " + json.dumps(state, ensure_ascii=False),
            },
            *context.recent_messages[-8:],
            {"role": "user", "content": message[:2000]},
        ]

    def _filters(self, raw: object, message: str) -> SearchFilters:
        safe = {}
        evidence = search_clause(message)
        for key, value in (raw if isinstance(raw, dict) else {}).items():
            if key not in SearchFilters.model_fields or value is None:
                continue
            if key in {"make", "model", "trim", "source"}:
                if isinstance(value, str) and mentioned_text(value, evidence):
                    safe[key] = value
            elif (
                isinstance(value, int)
                and not isinstance(value, bool)
                and amount_mentioned(value, evidence)
                and (
                    key not in {"min_price_aed", "max_price_aed"}
                    or not NON_AED_RE.search(message)
                )
            ):
                safe[key] = value
        makes, models = self.tools.inventory_catalog()
        safe.update(explicit_filters(message, makes, models))
        return SearchFilters.model_validate(safe)

    @staticmethod
    def _lead(raw: object, message: str) -> LeadUpdate | None:
        safe = {}
        for key, value in (raw if isinstance(raw, dict) else {}).items():
            if key not in LeadUpdate.model_fields or value is None:
                continue
            if (
                (
                    key == "contact_email"
                    and isinstance(value, str)
                    and value in EMAIL_RE.findall(message)
                )
                or (
                    key == "phone"
                    and isinstance(value, str)
                    and value in PHONE_RE.findall(message)
                )
                or (
                    key in {"desired_make", "desired_model", "desired_body_type"}
                    and isinstance(value, str)
                    and mentioned_text(value, message)
                )
                or (
                    key in {"budget_min_aed", "budget_max_aed"}
                    and isinstance(value, int)
                    and amount_mentioned(value, message)
                    and not NON_AED_RE.search(message)
                )
            ):
                safe[key] = value
            elif key == "needs" and isinstance(value, list):
                safe[key] = [
                    item
                    for item in value
                    if isinstance(item, str) and item.casefold() in message.casefold()
                ][:5]
        try:
            return LeadUpdate.model_validate(safe) if safe else None
        except ValidationError:
            return None

    @staticmethod
    def _slot(raw: object, message: str) -> datetime | None:
        if not isinstance(raw, str) or not re.search(
            r"\b(?:\d{1,2}[:.]\d{2}|\d{1,2}\s*(?:am|pm))\b", message, re.IGNORECASE
        ):
            return None
        if not re.search(
            r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b(?:mon|tue|wed|thu|fri|sat|sun)(?:day)?\b|\b(?:tomorrow|today)\b",
            message,
            re.IGNORECASE,
        ):
            return None
        try:
            value = datetime.fromisoformat(raw)
            value = (
                value.replace(tzinfo=ZoneInfo("Asia/Dubai"))
                if value.tzinfo is None
                else value
            )
            local = value.astimezone(ZoneInfo("Asia/Dubai"))
            stated_date = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", message)
            if (
                stated_date
                and local.date() != datetime.fromisoformat(stated_date.group(1)).date()
            ):
                return None
            stated_time = re.search(r"\b(\d{1,2}):(\d{2})\b", message)
            if stated_time and (local.hour, local.minute) != (
                int(stated_time.group(1)),
                int(stated_time.group(2)),
            ):
                return None
            stated_ampm = re.search(r"\b(\d{1,2})\s*(am|pm)\b", message, re.IGNORECASE)
            if stated_ampm:
                hour = int(stated_ampm.group(1)) % 12 + (
                    12 if stated_ampm.group(2).lower() == "pm" else 0
                )
                if local.hour != hour:
                    return None
            weekdays = (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
            for index, day in enumerate(weekdays):
                if (
                    re.search(r"\b" + day + r"\b", message, re.IGNORECASE)
                    and local.weekday() != index
                ):
                    return None
            today = datetime.now(ZoneInfo("Asia/Dubai")).date()
            if re.search(
                r"\btomorrow\b", message, re.IGNORECASE
            ) and local.date() != today + timedelta(days=1):
                return None
            if (
                re.search(r"\btoday\b", message, re.IGNORECASE)
                and local.date() != today
            ):
                return None
            return value
        except ValueError:
            return None

    @staticmethod
    def _stated_slot(message: str) -> str | None:
        """Pass an explicitly written Dubai date/time to the booking validator."""
        date = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", message)
        clock = re.search(r"\b(\d{1,2}):(\d{2})\b", message)
        if date and clock:
            return (
                f"{date.group(1)}T{int(clock.group(1)):02d}:{clock.group(2)}:00+04:00"
            )
        return None

    def run(self, body: ChatRequest) -> ChatResponse:
        context = self.tools.get_session_context(body.session_id)
        if context is None:
            raise LookupError("Session not found")
        if body.user_id is not None and body.user_id != context.user_id:
            raise SessionOwnershipError("Session belongs to another user")
        message = body.message.strip()
        if is_out_of_scope(message):
            reply = (
                "I can help with dubizzle cars, vehicle details, preferences, "
                "and viewing requests."
            )
            self.tools.memory.record_turn(body.session_id, message, reply)
            return ChatResponse(message=reply, session_id=body.session_id)
        profile = self.tools.get_user_memory(context.user_id)
        ref_id, reference_error = resolve_reference(message, context)
        if reference_error:
            self.tools.memory.record_turn(body.session_id, message, reference_error)
            return ChatResponse(message=reference_error, session_id=body.session_id)
        memory_kind = (
            "liked"
            if LIKED_MEMORY_RE.search(message)
            else "preferences"
            if PREFERENCE_MEMORY_RE.search(message)
            else "all"
            if GENERAL_MEMORY_RE.search(message)
            else None
        )
        calls = (
            [ToolCall("get_user_memory", {})]
            if memory_kind
            else self.model.plan(self._messages(context, profile, message), TOOLS)
        )
        allowed_names = {tool["function"]["name"] for tool in TOOLS}
        calls = [call for call in calls if call.name in allowed_names]
        names = {call.name for call in calls}
        if BOOKING_RE.search(message):
            # Viewing requests reach the slot validator when the planner misses them.
            calls = [
                call
                for call in calls
                if call.name not in {"get_car_details", "search_inventory", "greet"}
            ]
            if not any(call.name == "create_booking" for call in calls):
                calls.insert(
                    0,
                    ToolCall(
                        "create_booking",
                        {
                            "listing_id": ref_id or context.selected_car_id,
                            "proposed_at": self._stated_slot(message),
                        },
                    ),
                )
        elif ref_id and LIKE_RE.search(message):
            # An explicit like must survive a missed or incorrect planner action.
            calls = [call for call in calls if call.name != "remember_liked_car"]
            calls.insert(0, ToolCall("remember_liked_car", {"listing_id": ref_id}))
        elif ref_id and not SEARCH_RE.search(message):
            # Follow-ups target the resolved listing if the planner searches again.
            calls = [
                call
                for call in calls
                if call.name not in {"search_inventory", "get_car_details"}
            ]
            calls.insert(0, ToolCall("get_car_details", {"listing_id": ref_id}))
        elif ref_id and not names.intersection(
            {
                "search_inventory",
                "get_car_details",
                "create_booking",
                "remember_liked_car",
            }
        ):
            calls.insert(0, ToolCall("get_car_details", {"listing_id": ref_id}))

        lines: list[str] = []
        cars = []
        search_ids = active_filters = selected_id = None
        booking_recorded = False
        lead_data: dict = {}
        for call in calls[:5]:
            args = call.arguments
            if call.name == "search_inventory":
                try:
                    filters = self._filters(args.get("filters"), message)
                except ValidationError:
                    lines.append(
                        "The search filters conflict. Please clarify the range "
                        "you want."
                    )
                    continue
                semantic = args.get("semantic_query")
                if not isinstance(semantic, str) or not semantic.strip():
                    semantic = None
                elif semantic.casefold() not in message.casefold():
                    # Embed user wording only; model paraphrases may add requirements.
                    semantic = message
                if NON_AED_RE.search(message) and re.search(
                    r"\b(?:under|below|budget|price|cost)\b", message, re.IGNORECASE
                ):
                    lines.append(
                        "Please give your budget in AED so I can apply it accurately."
                    )
                    continue
                top_k = args.get("top_k", 5)
                top_k = min(max(top_k, 1), 10) if isinstance(top_k, int) else 5
                found = self.tools.search_inventory(
                    filters, semantic_query=semantic, top_k=top_k
                )
                cars = found
                search_ids = [car.listing_id for car in found]
                active_filters = filters.model_dump(exclude_none=True)
                lines.append(
                    "I found these listings: "
                    + "; ".join(
                        f"{i}. {car.listing_id} — "
                        f"{car.year} {car.make} {car.model} {car.trim}"
                        for i, car in enumerate(found, 1)
                    )
                    + "."
                    if found
                    else "I couldn't find a listing that matches those requirements."
                )
                for source, target in (
                    ("make", "desired_make"),
                    ("model", "desired_model"),
                    ("min_price_aed", "budget_min_aed"),
                    ("max_price_aed", "budget_max_aed"),
                ):
                    if source in active_filters:
                        lead_data[target] = active_filters[source]
            elif call.name == "get_car_details":
                listing_id = ref_id or args.get("listing_id")
                if not isinstance(listing_id, str) or (
                    ref_id is None
                    and listing_id not in context.last_search_results
                    and listing_id != context.selected_car_id
                ):
                    continue
                car = self.tools.get_car_details(listing_id)
                if car is None:
                    lines.append("That listing is not in the inventory.")
                    continue
                selected_id, cars = car.listing_id, [car]
                lines.append(factual_answer(car, message, args.get("attribute")))
            elif call.name == "get_user_memory":
                current = self.tools.get_user_memory(context.user_id)
                parts = []
                if current:
                    if memory_kind != "liked":
                        if memory_kind is None or memory_kind == "all":
                            parts.append(f"your name is {current.display_name}")
                        if current.preferred_makes:
                            parts.append(
                                "preferred makes: " + ", ".join(current.preferred_makes)
                            )
                        if current.preferred_models:
                            parts.append(
                                "preferred models: "
                                + ", ".join(current.preferred_models)
                            )
                        if current.budget_max_aed is not None:
                            parts.append(f"budget up to AED {current.budget_max_aed:,}")
                        if current.budget_min_aed is not None:
                            parts.append(f"budget from AED {current.budget_min_aed:,}")
                        if current.preferred_body_type:
                            parts.append(f"body type: {current.preferred_body_type}")
                        if current.preferred_colors:
                            parts.append(
                                "colors: " + ", ".join(current.preferred_colors)
                            )
                        if current.min_year is not None:
                            parts.append(f"minimum year: {current.min_year}")
                        if current.max_mileage_km is not None:
                            parts.append(
                                f"maximum mileage: {current.max_mileage_km:,} km"
                            )
                        if current.other_preferences:
                            parts.append(
                                "other preferences: "
                                + ", ".join(current.other_preferences)
                            )
                    if memory_kind != "preferences" and current.liked_car_ids:
                        parts.append("liked cars: " + ", ".join(current.liked_car_ids))
                lines.append(
                    "I remember " + "; ".join(parts) + "."
                    if parts
                    else "I don't have that saved yet."
                )
            elif call.name == "update_user_preferences":
                try:
                    update = PreferenceUpdate.model_validate(args.get("updates", {}))
                    safe = allowed_preference_updates(
                        message, update.model_dump(exclude_none=True)
                    )
                    if safe:
                        self.tools.update_user_preferences(context.user_id, safe)
                        lines.append("I've saved that vehicle preference.")
                except (ValidationError, ValueError):
                    pass
            elif call.name == "remember_liked_car":
                listing_id = ref_id or args.get("listing_id")
                if (
                    LIKE_RE.search(message)
                    and isinstance(listing_id, str)
                    and (
                        listing_id == ref_id
                        or listing_id in context.last_search_results
                    )
                    and self.tools.remember_liked_car(context.user_id, listing_id)
                ):
                    selected_id = listing_id
                    lines.append(f"I've saved {listing_id} to your liked cars.")
            elif call.name == "create_booking":
                listing_id = ref_id or args.get("listing_id")
                when = (
                    self._slot(args.get("proposed_at"), message)
                    if BOOKING_RE.search(message)
                    else None
                )
                if not isinstance(listing_id, str) or (
                    listing_id != ref_id
                    and listing_id not in context.last_search_results
                    and listing_id != context.selected_car_id
                ):
                    lines.append("Which listing would you like to view?")
                elif when is None:
                    lines.append(
                        "Please give a date and time for the viewing in Dubai time."
                    )
                else:
                    try:
                        booking = self.tools.create_booking(
                            context.user_id, body.session_id, listing_id, when
                        )
                        selected_id = listing_id
                        booking_recorded = True
                        lines.append(
                            f"Viewing request {booking.booking_id} for {listing_id} "
                            f"on {booking.proposed_at:%Y-%m-%d at %H:%M} Dubai time "
                            "was recorded. Slot availability is not confirmed."
                        )
                    except BookingError as exc:
                        lines.append(str(exc))
                    except LookupError:
                        lines.append("That listing is not in the inventory.")
            elif call.name == "save_lead":
                update = self._lead(args.get("update"), message)
                if update:
                    lead_data.update(update.model_dump(exclude_none=True))
            elif call.name == "get_session_context":
                if context.selected_car_id:
                    lines.append(f"The selected listing is {context.selected_car_id}.")
                elif context.last_search_results:
                    lines.append(
                        "The previous results were "
                        + ", ".join(context.last_search_results)
                        + "."
                    )
            elif call.name == "greet":
                lines.append(
                    "Hello! I can help you find cars on dubizzle or arrange a "
                    "viewing request."
                )
            elif call.name == "decline_out_of_scope":
                lines.append(
                    "I can help with dubizzle cars, vehicle details, preferences, "
                    "and viewing requests."
                )

        email = EMAIL_RE.search(message)
        if email:
            lead_data["contact_email"] = email.group()
        phone = PHONE_RE.search(message)
        if phone:
            lead_data["phone"] = phone.group()
        body_type = re.search(
            r"\b(?:SUV|sedan|coupe|hatchback|pickup|convertible|wagon)\b",
            message,
            re.IGNORECASE,
        )
        if body_type and (search_ids is not None or lead_data):
            lead_data["desired_body_type"] = (
                body_type.group().upper()
                if body_type.group().lower() == "suv"
                else body_type.group().title()
            )
        if lead_data:
            try:
                self.tools.save_lead(
                    context.user_id, LeadUpdate.model_validate(lead_data)
                )
            except ValidationError:
                pass
        if not lines and (email or phone):
            lines.append("Thanks, I've saved your contact details for follow-up.")
        if not lines:
            if ref_id:
                car = self.tools.get_car_details(ref_id)
                if car:
                    selected_id, cars = car.listing_id, [car]
                    lines.append(factual_answer(car, message))
                else:
                    lines.append("That listing is not in the inventory.")
            elif re.search(r"\b(?:hi|hello|hey)\b", message, re.IGNORECASE):
                lines.append(
                    "Hello! I can help you find cars on dubizzle or arrange a "
                    "viewing request."
                )
            else:
                lines.append(
                    "Tell me what car you want, or ask about a listing you've "
                    "seen here."
                )
        next_input = None
        if search_ids or booking_recorded or lead_data:
            lead = self.tools.leads.get_lead(context.user_id) or {}
            asked = " ".join(
                item["content"]
                for item in context.recent_messages
                if item["role"] == "assistant"
            ).casefold()
            if (
                booking_recorded
                and not (lead.get("contact_email") or lead.get("phone"))
                and "email or phone" not in asked
            ):
                next_input = (
                    "Would you like to share an email or phone number for follow-up?"
                )
            elif (
                not (
                    lead.get("desired_body_type")
                    or (profile and profile.preferred_body_type)
                )
                and "preferred body type" not in asked
            ):
                next_input = "Do you have a preferred body type or other must-haves?"
            elif (
                not (
                    lead.get("budget_min_aed")
                    or lead.get("budget_max_aed")
                    or (profile and (profile.budget_min_aed or profile.budget_max_aed))
                )
                and "budget in aed" not in asked
            ):
                next_input = "What budget in AED are you considering?"
            elif (
                (lead.get("budget_min_aed") or lead.get("budget_max_aed"))
                and (
                    lead.get("desired_make")
                    or lead.get("desired_model")
                    or lead.get("desired_body_type")
                    or lead.get("needs")
                )
                and not (lead.get("contact_email") or lead.get("phone"))
                and "email or phone" not in asked
            ):
                next_input = (
                    "Would you like to share an email or phone number for follow-up?"
                )
        if next_input:
            lines.append(next_input)
        reply = " ".join(lines)
        self.tools.memory.record_turn(
            body.session_id,
            message,
            reply,
            search_ids=search_ids,
            selected_car_id=selected_id,
            active_filters=active_filters,
        )
        return ChatResponse(
            message=reply,
            session_id=body.session_id,
            cars=[CarResponse.model_validate(car) for car in cars],
            listing_ids=[car.listing_id for car in cars],
            next_input=next_input,
        )

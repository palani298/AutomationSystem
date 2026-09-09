from __future__ import annotations

import json
import re
from typing import Any

from capability_forge.config import settings
from capability_forge.schemas.artifact import Locator, LocatorStrategy
from capability_forge.schemas.run import AgentDecision

SYSTEM = """You operate a legacy credit-union back-office web app.
You receive an accessibility-tree snapshot plus a goal.
Reply with ONE JSON object, no markdown.

Allowed actions: click, fill, press, extract, dismiss, wait, done, fail, escalate.

Schema:
{
  "thought": "short",
  "action": "click|fill|press|extract|dismiss|wait|done|fail|escalate",
  "locator": {
    "strategy": "role_name|label|placeholder|text|title|css",
    "role": "textbox|button|link|...",
    "name": "accessible name",
    "label": "",
    "text": "",
    "placeholder": "",
    "css": "",
    "frame_selector": "iframe.search-frame or iframe[title=\\"Member search form\\"] if the control is inside that iframe"
  },
  "value": "only for fill",
  "extract_as": "output field name for extract",
  "outputs": {"field": "value"} ,
  "reason": "why done/fail/escalate"
}

Rules:
- Prefer role_name (role + accessible name) over CSS.
- The search field lives INSIDE an iframe titled "Member search form". Set frame_selector when acting there.
- Parameterize: if the goal mentions a member number, type that number; do not invent others.
- When the goal is met, action=done and fill outputs (member_name, savings_balance, confirmation_id if present).
- If you see "No records found" after a real search, action=done with outputs {} and reason MEMBER_NOT_FOUND — that is a business outcome, not a crash.
- If you are looping or cannot find a control, escalate.
- Never close an account or click irreversible monetary actions.
- Dismiss system notices if they block the form.
"""


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text)
        text = re.sub(r"```$", "", text.strip())
    return json.loads(text)


def _to_decision(raw: dict[str, Any]) -> AgentDecision:
    loc_raw = raw.get("locator") or None
    locator = Locator.model_validate(loc_raw) if loc_raw else None
    if locator and locator.strategy == LocatorStrategy.ROLE_NAME and not locator.role:
        locator.role = "button"
    return AgentDecision(
        thought=str(raw.get("thought") or ""),
        action=raw.get("action") or "fail",
        locator=locator,
        value=raw.get("value"),
        extract_as=raw.get("extract_as"),
        outputs={k: str(v) for k, v in (raw.get("outputs") or {}).items()},
        reason=str(raw.get("reason") or ""),
    )


class LLMClient:
    async def decide(self, goal: str, observation: dict, history: list[str]) -> AgentDecision:
        user = (
            f"GOAL: {goal}\n"
            f"URL: {observation.get('url')}\n"
            f"TITLE: {observation.get('title')}\n"
            f"ARIA:\n{observation.get('aria')}\n"
            f"RECENT:\n" + "\n".join(history[-8:])
        )
        if settings.llm_provider == "anthropic":
            raw = await self._anthropic(user)
        else:
            raw = await self._openai(user)
        return _to_decision(raw)

    async def _openai(self, user: str) -> dict[str, Any]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key or None)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        return _parse_json(resp.choices[0].message.content or "{}")

    async def _anthropic(self, user: str) -> dict[str, Any]:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key or None)
        resp = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=800,
            temperature=0,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return _parse_json(text)

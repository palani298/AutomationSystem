from __future__ import annotations

from playwright.async_api import Page

from capability_forge.browser.locators import resolve_first_visible
from capability_forge.config import settings
from capability_forge.schemas.artifact import Locator, Step, StepAction


async def observe(page: Page) -> dict:
    aria = ""
    try:
        aria = await page.locator("body").aria_snapshot()
    except Exception:
        aria = await page.inner_text("body")
    title = await page.title()
    return {
        "url": page.url,
        "title": title,
        "aria": aria[:12000],
    }


def resolve_value(step: Step, params: dict[str, str]) -> str | None:
    if step.value_from:
        if step.value_from.startswith("params."):
            return params.get(step.value_from.split(".", 1)[1])
        return params.get(step.value_from)
    return step.literal


async def execute_step(page: Page, step: Step, params: dict[str, str]) -> str | None:
    timeout = settings.action_timeout_ms
    if step.action is StepAction.NAVIGATE:
        if not step.url:
            raise ValueError("navigate step missing url")
        await page.goto(step.url, wait_until="domcontentloaded")
        return None
    if step.action is StepAction.WAIT:
        await page.wait_for_timeout(step.wait_ms or 400)
        return None

    locators: list[Locator] = list(step.locators)
    if not locators:
        raise ValueError(f"step {step.id} has no locators")
    target, _ = await resolve_first_visible(page, locators, timeout_ms=timeout)

    if step.action is StepAction.CLICK:
        await target.click(timeout=timeout)
    elif step.action is StepAction.FILL:
        value = resolve_value(step, params)
        if value is None:
            raise ValueError(f"step {step.id} missing fill value")
        await target.fill(value, timeout=timeout)
    elif step.action is StepAction.SELECT:
        value = resolve_value(step, params)
        if value is None:
            raise ValueError(f"step {step.id} missing select value")
        await target.select_option(value, timeout=timeout)
    elif step.action is StepAction.PRESS:
        await target.press(step.literal or "Enter", timeout=timeout)
    elif step.action is StepAction.DISMISS:
        await target.click(timeout=timeout)
    elif step.action is StepAction.EXTRACT:
        text = (await target.inner_text()).strip()
        return text
    else:
        raise ValueError(f"unsupported action {step.action}")
    return None

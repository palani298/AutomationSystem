from __future__ import annotations

from playwright.async_api import FrameLocator, Locator as PwLocator, Page

from capability_forge.schemas.artifact import Locator, LocatorStrategy


def resolve_one(page: Page, loc: Locator) -> PwLocator:
    root: Page | FrameLocator = page
    if loc.frame_selector:
        root = page.frame_locator(loc.frame_selector)

    if loc.strategy is LocatorStrategy.ROLE_NAME:
        if not loc.role:
            raise ValueError("role_name locator requires role")
        target = root.get_by_role(loc.role, name=loc.name, exact=loc.exact)
    elif loc.strategy is LocatorStrategy.LABEL:
        target = root.get_by_label(loc.label or loc.name or "", exact=loc.exact)
    elif loc.strategy is LocatorStrategy.PLACEHOLDER:
        target = root.get_by_placeholder(loc.placeholder or loc.name or "", exact=loc.exact)
    elif loc.strategy is LocatorStrategy.TEXT:
        target = root.get_by_text(loc.text or loc.name or "", exact=loc.exact)
    elif loc.strategy is LocatorStrategy.TITLE:
        target = root.get_by_title(loc.title or loc.name or "", exact=loc.exact)
    elif loc.strategy is LocatorStrategy.CSS:
        if not loc.css:
            raise ValueError("css locator requires css")
        target = root.locator(loc.css)
    else:
        raise ValueError(f"unknown locator strategy: {loc.strategy}")

    if loc.nth is not None:
        target = target.nth(loc.nth)
    return target


async def resolve_first_visible(
    page: Page,
    locators: list[Locator],
    timeout_ms: int = 2500,
) -> tuple[PwLocator, Locator]:
    last_error: Exception | None = None
    for loc in locators:
        try:
            target = resolve_one(page, loc)
            await target.first.wait_for(state="visible", timeout=timeout_ms)
            return target.first, loc
        except Exception as exc:
            last_error = exc
    raise LookupError(f"no locator resolved; last error: {last_error}")


async def describe_locator(page: Page, loc: Locator) -> Locator:
    """Best-effort enrichment so the artifact stores more than the LLM guessed."""
    try:
        el, _ = await resolve_first_visible(page, [loc], timeout_ms=800)
        role = await el.get_attribute("role")
        name = (await el.inner_text() or "").strip()
        if len(name) > 80:
            name = name[:80]
        extras: list[Locator] = []
        if role and name:
            extras.append(
                Locator(strategy=LocatorStrategy.ROLE_NAME, role=role, name=name, frame_selector=loc.frame_selector)
            )
        label = await el.get_attribute("aria-label")
        if label:
            extras.append(
                Locator(strategy=LocatorStrategy.LABEL, label=label, frame_selector=loc.frame_selector)
            )
        return loc if not extras else loc
    except Exception:
        return loc

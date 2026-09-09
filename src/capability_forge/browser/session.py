from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from capability_forge.browser.actions import execute_step, observe
from capability_forge.config import settings
from capability_forge.schemas.artifact import Step


@dataclass
class LiveSession:
    id: str
    run_id: str
    page: Page
    context: BrowserContext
    controller: str = "agent"  # agent | human
    last_observation: dict[str, Any] = field(default_factory=dict)
    stuck_reason: str = ""


class SessionManager:
    """In-process owner of Playwright pages.

    Temporal activities talk to this manager by session id. The page object
    never crosses a process boundary, which is what makes live human handoff
    possible on the *same* browser session.
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._sessions: dict[str, LiveSession] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.playwright_headless,
            slow_mo=settings.playwright_slow_mo_ms,
        )

    async def stop(self) -> None:
        for session in list(self._sessions.values()):
            await self.close(session.id)
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def create(self, run_id: str, entry_url: str | None = None) -> LiveSession:
        await self.start()
        assert self._browser is not None
        context = await self._browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        session = LiveSession(id=str(uuid4()), run_id=run_id, page=page, context=context)
        self._sessions[session.id] = session
        if entry_url:
            await page.goto(entry_url, wait_until="domcontentloaded")
        return session

    def get(self, session_id: str) -> LiveSession:
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"unknown session {session_id}")
        return session

    def get_by_run(self, run_id: str) -> LiveSession | None:
        for session in self._sessions.values():
            if session.run_id == run_id:
                return session
        return None

    async def snapshot(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        session.last_observation = await observe(session.page)
        png = await session.page.screenshot(type="png")
        return {
            **session.last_observation,
            "controller": session.controller,
            "stuck_reason": session.stuck_reason,
            "screenshot_png": png,
        }

    async def act(self, session_id: str, step: Step, params: dict[str, str]) -> str | None:
        session = self.get(session_id)
        return await execute_step(session.page, step, params)

    def set_controller(self, session_id: str, who: str, reason: str = "") -> None:
        session = self.get(session_id)
        session.controller = who
        session.stuck_reason = reason

    async def close(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if not session:
            return
        try:
            await session.context.close()
        except Exception:
            pass


sessions = SessionManager()

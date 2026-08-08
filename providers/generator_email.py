"""Temp email via generator.email — browser-based approach.

Two approaches, both proven working:
1. wait_for_otp(): Same-tab navigate-away (for when tab is already on blackbox)
2. wait_for_otp_new_tab(): Open fresh new tab for inbox check (no stale data)

Key DOM structure (MCP Playwright verified):
- SITE_DATA: {cur_user, cur_domain, num_mess, mess_id_raw}
- .mess_bodiyy: message body text
- Regex: \\b(\\d{6})\\b to extract OTP
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import nodriver as uc

from config import Config


class GeneratorEmailClient:
    """Manages a generator.email session via nodriver browser."""

    def __init__(self, browser: uc.Browser):
        self._browser = browser
        self._tab: Optional[uc.Tab] = None
        self._email: str = ""
        self._domain: str = ""

    async def open(self, preferred_domain: str = "senvas.me") -> str:
        """Open generator.email inbox directly with preferred domain."""
        import secrets
        import string

        random_user = ''.join(
            secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10)
        )
        domain = preferred_domain or "senvas.me"
        inbox_url = f"https://generator.email/{domain}/{random_user}"
        self._tab = await self._browser.get(inbox_url)
        await self._tab.sleep(5)

        for attempt in range(3):
            site_data = await self._tab.evaluate(
                '(function() { var d = window.SITE_DATA || {}; '
                'return { user: d.cur_user || "", domain: d.cur_domain || "" }; })()'
            )
            if site_data and isinstance(site_data, dict):
                self._email = site_data.get("user", "")
                self._domain = site_data.get("domain", "")
                if self._email and self._domain:
                    break

            if not self._email:
                self._email = await self._tab.evaluate(
                    '(function() { var el = document.getElementById("userName"); '
                    'return el ? el.value : ""; })()'
                ) or ""
            if not self._domain:
                self._domain = await self._tab.evaluate(
                    '(function() { var el = document.getElementById("domainName2") || '
                    'document.getElementById("domainName"); return el ? el.value : ""; })()'
                ) or ""
            if self._email and self._domain:
                break

            if attempt < 2:
                print(f"  [generator.email] SITE_DATA empty, reload #{attempt+1}...")
                try:
                    await self._tab.evaluate("location.reload()")
                    await self._tab.sleep(5)
                except Exception:
                    pass

        if not self._email or not self._domain:
            raise RuntimeError("Failed to read email from generator.email")

        full_email = f"{self._email}@{self._domain}"
        print(f"  [generator.email] {full_email}")
        return full_email

    async def wait_for_otp_new_tab(self, cfg: Config) -> Optional[str]:
        """Open a NEW TAB to check inbox for OTP.

        PROVEN approach from test_clean.py: new tab gets fresh server-rendered
        data (num_mess > 0), while old tabs show stale num_mess=0.

        Returns the 6-digit code, or None on timeout.
        Also stores the tab used (self._tab) for caller to reuse.
        """
        inbox_url = f"https://generator.email/{self._domain}/{self._email}"
        deadline = time.monotonic() + cfg.verify_poll_timeout
        poll_count = 0

        try:
            # Open a fresh new tab for inbox
            print(f"  [generator.email] Opening fresh inbox tab...")
            self._tab = await self._browser.get(inbox_url, new_tab=True)
            await self._tab.sleep(6)

            while True:
                poll_count += 1

                # Check SITE_DATA for message count
                try:
                    result = await self._tab.evaluate(
                        '(function() { '
                        '  var d = window.SITE_DATA || {}; '
                        '  return { '
                        '    num_mess: parseInt(d.num_mess || 0, 10), '
                        '    user: d.cur_user || "", '
                        '    domain: d.cur_domain || "" '
                        '  }; '
                        '})()'
                    )
                except Exception:
                    result = None

                num_mess = 0
                if result and isinstance(result, dict):
                    num_mess = result.get("num_mess", 0)

                if num_mess > 0:
                    otp = await self._extract_otp(self._tab)
                    if otp:
                        return otp

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    print(f"  [generator.email] Timeout after {poll_count} polls")
                    return None

                if poll_count % 5 == 0:
                    print(f"  [generator.email] Poll #{poll_count} (messages: {num_mess})")

                # Reload for next poll
                try:
                    await self._tab.evaluate("location.reload()")
                    await self._tab.sleep(4)
                except Exception:
                    pass

                await asyncio.sleep(min(cfg.verify_poll_interval, remaining))

        except Exception as e:
            print(f"  [generator.email] Error: {e}")
            return None

    async def wait_for_otp(self, cfg: Config, tab: Optional[uc.Tab] = None) -> Optional[str]:
        """Navigate to inbox on given tab and poll for OTP.

        Same-tab approach: navigates away from blackbox to check inbox.
        Blackbox OTP state is server-side cookies, so safe to navigate.

        Returns the 6-digit code, or None on timeout.
        """
        use_tab = tab or self._tab
        if not use_tab:
            raise RuntimeError("No tab available for inbox check")

        inbox_url = f"https://generator.email/{self._domain}/{self._email}"
        deadline = time.monotonic() + cfg.verify_poll_timeout
        poll_count = 0

        print(f"  [generator.email] Navigating to inbox...")
        await use_tab.get(inbox_url)
        await use_tab.sleep(5)

        try:
            while True:
                poll_count += 1

                if poll_count > 1:
                    try:
                        await use_tab.evaluate("location.reload()")
                        await use_tab.sleep(5)
                    except Exception:
                        pass

                try:
                    result = await use_tab.evaluate(
                        '(function() { '
                        '  var d = window.SITE_DATA || {}; '
                        '  return { '
                        '    num_mess: parseInt(d.num_mess || 0, 10), '
                        '    user: d.cur_user || "", '
                        '    domain: d.cur_domain || "" '
                        '  }; '
                        '})()'
                    )
                except Exception:
                    result = None

                num_mess = 0
                if result and isinstance(result, dict):
                    num_mess = result.get("num_mess", 0)

                if num_mess > 0:
                    otp = await self._extract_otp(use_tab)
                    if otp:
                        return otp

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    print(f"  [generator.email] Timeout after {poll_count} polls")
                    return None

                if poll_count % 5 == 0:
                    print(f"  [generator.email] Poll #{poll_count} (messages: {num_mess})")

                await asyncio.sleep(min(cfg.verify_poll_interval, remaining))

        except Exception as e:
            print(f"  [generator.email] Error: {e}")
            return None

    async def _extract_otp(self, tab: uc.Tab) -> Optional[str]:
        """Extract OTP from .mess_bodiyy element."""
        try:
            result = await tab.evaluate(
                '(function() { '
                '  var bodiyy = document.querySelector(".mess_bodiyy"); '
                '  if (!bodiyy) return null; '
                '  var text = bodiyy.innerText || ""; '
                '  if (!text) return null; '
                '  var match = text.match(/\\b(\\d{6})\\b/); '
                '  return match ? match[1] : null; '
                '})()'
            )
            if result and len(str(result)) == 6:
                code = str(result)
                print(f"  [generator.email] OTP found: {code}")
                return code

            result2 = await tab.evaluate(
                '(function() { '
                '  var body = document.getElementById("mail-summary-body"); '
                '  if (!body) return null; '
                '  var text = body.innerText || ""; '
                '  if (!text) return null; '
                '  var match = text.match(/\\b(\\d{6})\\b/); '
                '  return match ? match[1] : null; '
                '})()'
            )
            if result2 and len(str(result2)) == 6:
                code = str(result2)
                print(f"  [generator.email] OTP found (body): {code}")
                return code

        except Exception as e:
            print(f"  [generator.email] extract error: {e}")
        return None

    async def close(self):
        if self._tab:
            try:
                await self._tab.close()
            except Exception:
                pass
            self._tab = None

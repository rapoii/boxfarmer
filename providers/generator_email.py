"""Temp email via generator.email — browser-based approach.

Two approaches, both proven working:
1. wait_for_otp(): Same-tab navigate-away (for when tab is already on blackbox)
2. wait_for_otp_new_tab(): Open fresh new tab for inbox check (no stale data)

Key DOM structure (MCP Playwright verified):
- SITE_DATA: {cur_user, cur_domain, num_mess, mess_id_raw}
- .mess_bodiyy: message body text
- Regex: \\b(\\d{6})\\b to extract OTP
- "Generate new e-mail" button: #genrandom (randomizes domain + username)
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

    # Domains that can't receive Blackbox emails
    UNSUPPORTED_DOMAINS = {"generator.email", "dharmadi.com", "dharmadi"}

    def __init__(self, browser: uc.Browser):
        self._browser = browser
        self._tab: Optional[uc.Tab] = None
        self._email: str = ""
        self._domain: str = ""

    async def open(self, preferred_domain: str = "") -> str:
        """Open generator.email and get a fresh email address.

        Two modes:
        - preferred_domain="" (default): click "Generate new e-mail" to get
          a random domain assigned by generator.email (recommended, avoids
          domain-level rate limits).
        - preferred_domain="example.com": navigate directly to that domain
          inbox with a random username.

        Returns the full email address (user@domain).
        """
        if preferred_domain:
            import secrets
            import string
            random_user = ''.join(
                secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10)
            )
            inbox_url = f"https://generator.email/{preferred_domain}/{random_user}"
            self._tab = await self._browser.get(inbox_url)
            await self._tab.sleep(5)
            await self._read_email_from_page()
        else:
            # Random mode: let generator.email pick domain (like grok_farmer)
            self._tab = await self._browser.get("https://generator.email")
            await self._tab.sleep(5)

            for gen_attempt in range(5):
                # Reset for each attempt
                self._email = ""
                self._domain = ""
                await self._read_email_from_page()

                if self._email and self._domain:
                    if self._domain not in self.UNSUPPORTED_DOMAINS:
                        break
                    print(f"  [generator.email] Domain {self._domain} unsupported, "
                          f"regenerating... (attempt {gen_attempt+1})")
                await self._click_generate()

        # Final fallback: retry reading if empty
        for attempt in range(3):
            if self._email and self._domain:
                break
            print(f"  [generator.email] SITE_DATA empty, reload #{attempt+1}...")
            try:
                await self._tab.evaluate("location.reload()")
                await self._tab.sleep(5)
            except Exception:
                pass
            self._email = ""
            self._domain = ""
            await self._read_email_from_page()

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
            print(f"  [generator.email] Opening fresh inbox tab...")
            self._tab = await self._browser.get(inbox_url, new_tab=True)
            await self._tab.sleep(6)

            while True:
                poll_count += 1

                num_mess = await self._check_num_mess(self._tab)

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

                num_mess = await self._check_num_mess(use_tab)

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

    async def _check_num_mess(self, tab: uc.Tab) -> int:
        """Check SITE_DATA.num_mess on a tab. Returns 0 on failure."""
        try:
            result = await tab.evaluate(
                '(function() { '
                '  var d = window.SITE_DATA || {}; '
                '  return parseInt(d.num_mess || 0, 10); '
                '})()'
            )
            return int(result or 0)
        except Exception:
            return 0

    async def _extract_otp(self, tab: uc.Tab) -> Optional[str]:
        """Extract 6-digit OTP from .mess_bodiyy or #mail-summary-body."""
        for selector, label in [
            (".mess_bodiyy", ""),
            ("#mail-summary-body", " (body)"),
        ]:
            try:
                result = await tab.evaluate(
                    f'(function() {{ '
                    f'  var el = document.querySelector("{selector}"); '
                    f'  if (!el) return null; '
                    f'  var text = el.innerText || ""; '
                    f'  if (!text) return null; '
                    f'  var match = text.match(/\\b(\\d{{6}})\\b/); '
                    f'  return match ? match[1] : null; '
                    f'}})()'
                )
                if result and len(str(result)) == 6:
                    code = str(result)
                    print(f"  [generator.email] OTP found{label}: {code}")
                    return code
            except Exception as e:
                print(f"  [generator.email] extract error ({label.strip() or selector}): {e}")
        return None

    async def _click_generate(self):
        """Click 'Generate new e-mail' button (#genrandom)."""
        try:
            btn = await self._tab.select("#genrandom", timeout=3)
            if btn:
                await btn.click()
                await self._tab.sleep(3)
        except Exception:
            try:
                btn = await self._tab.find("Generate new e-mail", best_match=True, timeout=3)
                if btn:
                    await btn.click()
                    await self._tab.sleep(3)
            except Exception:
                pass

    async def _read_email_from_page(self):
        """Read email username and domain from SITE_DATA or input fields."""
        # Try SITE_DATA first (server-rendered, most reliable)
        try:
            site_data = await self._tab.evaluate(
                '(function() { var d = window.SITE_DATA || {}; '
                'return { user: d.cur_user || "", domain: d.cur_domain || "" }; })()'
            )
            if site_data and isinstance(site_data, dict):
                self._email = site_data.get("user", "") or self._email
                self._domain = site_data.get("domain", "") or self._domain
        except Exception:
            pass

        # Fallback: read from input fields
        if not self._email:
            try:
                self._email = await self._tab.evaluate(
                    '(function() { var el = document.getElementById("userName"); '
                    'return el ? el.value : ""; })()'
                ) or self._email
            except Exception:
                pass

        if not self._domain:
            try:
                self._domain = await self._tab.evaluate(
                    '(function() { var el = document.getElementById("domainName2") || '
                    'document.getElementById("domainName"); return el ? el.value : ""; })()'
                ) or self._domain
            except Exception:
                pass

    async def close(self):
        if self._tab:
            try:
                await self._tab.close()
            except Exception:
                pass
            self._tab = None

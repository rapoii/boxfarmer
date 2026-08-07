"""Temp email via generator.email — hybrid browser + httpx approach.

Flow:
1. Open generator.email in browser → get random email + session cookies
2. Save cookies for httpx polling
3. Poll inbox via HTTP with saved cookies (no browser tab needed)
4. Fetch message source to extract OTP code

Advantages over catchmail.io:
- More domains available (less likely to be blocked by Blackbox)
- Browser-based (looks like real user)

Disadvantages:
- Requires browser session for initial setup (cookies)
- May hit CAPTCHA on heavy use
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Optional

import httpx
import nodriver as uc

from config import Config

_OTP_PATTERN = re.compile(r"\b(\d{6})\b")


class GeneratorEmailClient:
    """Manages a generator.email session — browser for setup, httpx for polling."""

    def __init__(self, browser: uc.Browser):
        self._browser = browser
        self._tab: Optional[uc.Tab] = None
        self._email: str = ""
        self._domain: str = ""
        self._cookies: dict = {}

    async def open(self) -> str:
        """Open generator.email and get a fresh random email address."""
        self._tab = await self._browser.get("https://generator.email/")
        await self._tab.sleep(4)

        # Read username from input#userName
        self._email = await self._tab.evaluate(
            '(function() { var el = document.getElementById("userName"); return el ? el.value : ""; })()'
        ) or ""
        self._domain = await self._tab.evaluate(
            '(function() { var el = document.getElementById("domainName2") || document.getElementById("domainName"); return el ? el.value : ""; })()'
        ) or ""

        if not self._email or not self._domain:
            raise RuntimeError("Failed to read email from generator.email")

        # Extract cookies from browser session for httpx polling
        try:
            cookies_raw = await self._tab.evaluate(
                'document.cookie'
            )
            if cookies_raw:
                for pair in cookies_raw.split(";"):
                    pair = pair.strip()
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        self._cookies[k.strip()] = v.strip()
        except:
            pass

        full_email = f"{self._email}@{self._domain}"
        print(f"  [generator.email] {full_email}")
        return full_email

    async def wait_for_otp(self, cfg: Config) -> Optional[str]:
        """Poll generator.email inbox for OTP code via HTTP."""
        deadline = time.monotonic() + cfg.verify_poll_timeout
        poll_count = 0
        seen_ids = set()

        base_url = f"https://generator.email/{self._domain}/{self._email}"

        async with httpx.AsyncClient(
            timeout=cfg.request_timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://generator.email/",
            },
            cookies=self._cookies,
        ) as client:
            while True:
                poll_count += 1

                try:
                    # Fetch inbox page
                    resp = await client.get(base_url)
                    if resp.status_code == 200:
                        html = resp.text

                        # Extract message IDs from the page
                        # generator.email embeds message IDs in various ways
                        message_ids = re.findall(r'data-mid="([^"]+)"', html)
                        if not message_ids:
                            message_ids = re.findall(r"mess_id\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
                        if not message_ids:
                            # Try to find onclick handlers with message IDs
                            message_ids = re.findall(r"showMail\(['\"]([^'\"]+)['\"]\)", html)
                        if not message_ids:
                            message_ids = re.findall(r'src=([^&"]+)', html)

                        new_ids = [mid for mid in message_ids if mid not in seen_ids]

                        if new_ids:
                            for mid in new_ids:
                                seen_ids.add(mid)
                                # Fetch message source
                                try:
                                    src_resp = await client.get(
                                        base_url,
                                        params={"src": mid},
                                    )
                                    if src_resp.status_code == 200:
                                        body = src_resp.text
                                        # Strip HTML tags
                                        text = re.sub(r'<[^>]+>', ' ', body)
                                        if "blackbox" in text.lower() or "verify" in text.lower() or "code" in text.lower():
                                            match = _OTP_PATTERN.search(text)
                                            if match:
                                                code = match.group(1)
                                                print(f"  [generator.email] OTP found: {code}")
                                                return code
                                except:
                                    continue

                        # Also check if there's a direct code in the page
                        if "blackbox" in html.lower() or "verify" in html.lower():
                            text = re.sub(r'<[^>]+>', ' ', html)
                            match = _OTP_PATTERN.search(text)
                            if match:
                                code = match.group(1)
                                print(f"  [generator.email] OTP found (direct): {code}")
                                return code

                except Exception as e:
                    if poll_count % 10 == 0:
                        print(f"  [generator.email] Poll error: {e}")

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None

                if poll_count % 5 == 0:
                    print(f"  [generator.email] Polling... ({poll_count})")

                await asyncio.sleep(min(cfg.verify_poll_interval, remaining))

    async def close(self):
        """Close the tab."""
        if self._tab:
            try:
                await self._tab.close()
            except:
                pass
            self._tab = None

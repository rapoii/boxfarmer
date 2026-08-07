"""Temp email via generator.email using a nodriver browser tab.

How it works:
1. Open generator.email in a new tab
2. Read the auto-generated email from the page
3. Poll the inbox (same tab) for OTP messages
4. Extract 6-digit code from email body

Advantages over catchmail.io:
- More domains available (less likely to be blocked)
- Browser-based, looks like real user
- No API key needed

Disadvantages:
- Requires a browser tab (can't use concurrently in same browser)
- May hit CAPTCHA on heavy use
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

import nodriver as uc

from config import Config

_OTP_PATTERN = re.compile(r"\b(\d{6})\b")


class GeneratorEmailClient:
    """Manages a generator.email session via nodriver."""

    def __init__(self, browser: uc.Browser):
        self._browser = browser
        self._tab: Optional[uc.Tab] = None
        self._email: str = ""
        self._domain: str = ""

    async def open(self) -> str:
        """Open generator.email and get a fresh random email address."""
        self._tab = await self._browser.get("https://generator.email/")
        await self._tab.sleep(4)

        # Read username from input#userName
        self._email = await self._tab.evaluate(
            '(function() { var el = document.getElementById("userName"); return el ? el.value : ""; })()'
        )
        self._domain = await self._tab.evaluate(
            '(function() { var el = document.getElementById("domainName2") || document.getElementById("domainName"); return el ? el.value : ""; })()'
        )

        if not self._email or not self._domain:
            # Fallback: parse from page
            full = await self._tab.evaluate(
                '(function() { var el = document.getElementById("mail"); return el ? el.value : ""; })()'
            )
            if full and "@" in full:
                self._email, self._domain = full.split("@", 1)

        if not self._email or not self._domain:
            raise RuntimeError("Failed to read email from generator.email")

        full_email = f"{self._email}@{self._domain}"
        print(f"  [generator.email] {full_email}")
        return full_email

    async def wait_for_otp(self, cfg: Config) -> Optional[str]:
        """Poll inbox for OTP code."""
        if not self._tab:
            raise RuntimeError("Tab not opened")

        deadline = time.monotonic() + cfg.verify_poll_timeout
        poll_count = 0

        while True:
            poll_count += 1

            # Click "Refresh" or poll inbox via JS
            try:
                # generator.email uses SSE/polling, but let's also click refresh if available
                await self._tab.evaluate(
                    '(function() { var btn = document.querySelector("#refresh_but, button[onclick*=refresh], .refresh-btn"); if(btn) btn.click(); })()'
                )
            except:
                pass

            await self._tab.sleep(2)

            # Check for new messages in the inbox area
            try:
                message_count = await self._tab.evaluate(
                    '(function() { return document.querySelectorAll("#email-table tr, .email-item, .mail_item, .inbox-item, .mess_item").length; })()'
                )

                if message_count and int(message_count) > 0:
                    # Try to read the first message
                    otp = await self._read_latest_otp()
                    if otp:
                        return otp

                    # Click on the first message to open it
                    try:
                        await self._tab.evaluate(
                            '(function() { var row = document.querySelector("#email-table tr, .email-item, .mail_item, .inbox-item, .mess_item"); if(row) row.click(); })()'
                        )
                        await self._tab.sleep(2)
                        otp = await self._read_latest_otp()
                        if otp:
                            return otp
                    except:
                        pass

            except:
                pass

            # Also check full page text for OTP
            try:
                page_text = await self._tab.evaluate("document.body.innerText") or ""
                # Only look for OTP if there's a blackbox-related message
                if "blackbox" in page_text.lower() or "verify" in page_text.lower() or "code" in page_text.lower():
                    match = _OTP_PATTERN.search(page_text)
                    if match:
                        code = match.group(1)
                        print(f"  [generator.email] OTP found: {code}")
                        return code
            except:
                pass

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None

            if poll_count % 5 == 0:
                print(f"  [generator.email] Polling... ({poll_count})")

            await asyncio.sleep(min(cfg.verify_poll_interval, remaining))

    async def _read_latest_otp(self) -> Optional[str]:
        """Try to extract OTP from visible message content."""
        try:
            # Get message body text
            body_text = await self._tab.evaluate(
                '(function() { '
                '  var el = document.querySelector("#email-body, .email-body, .mail-body, .message-body, .mess_body, .source-body"); '
                '  return el ? el.innerText : ""; '
                '})()'
            )
            if body_text:
                match = _OTP_PATTERN.search(body_text)
                if match:
                    return match.group(1)

            # Try innerHTML for hidden elements
            body_html = await self._tab.evaluate(
                '(function() { '
                '  var el = document.querySelector("#email-body, .email-body, .mail-body, .message-body, .mess_body, .source-body"); '
                '  return el ? el.innerHTML : ""; '
                '})()'
            )
            if body_html:
                # Strip tags
                text = re.sub(r'<[^>]+>', ' ', body_html)
                match = _OTP_PATTERN.search(text)
                if match:
                    return match.group(1)
        except:
            pass
        return None

    async def close(self):
        """Close the tab."""
        if self._tab:
            try:
                await self._tab.close()
            except:
                pass
            self._tab = None

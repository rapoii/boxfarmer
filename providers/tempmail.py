"""Catchmail.io temp email API (no browser needed)."""
from __future__ import annotations

import asyncio
import httpx
import re
import secrets
import string
from typing import Optional

from config import Config


def generate_email(domain: str = "catchmail.io") -> str:
    """Generate a random catchmail.io email address."""
    user = secrets.token_hex(6)
    return f"{user}@{domain}"


async def fetch_messages(email: str, page: int = 1) -> Optional[list]:
    """Fetch messages for an email from catchmail.io API."""
    url = f"https://api.catchmail.io/api/v1/mailbox?address={email}&page={page}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("messages", [])
    return None


def extract_otp_code(text: str) -> Optional[str]:
    """Extract OTP code from email text. Blackbox sends 6-digit codes."""
    digits = re.findall(r'\b(\d{6})\b', text)
    if digits:
        for d in digits:
            if not d.startswith("20"):
                return d
        return digits[0]

    dash = re.findall(r'\b([A-Z0-9]{3}-[A-Z0-9]{3})\b', text)
    if dash:
        return dash[0].replace("-", "")

    return None


async def wait_for_otp(email: str, cfg: Config) -> Optional[str]:
    """Poll catchmail.io for Blackbox.ai verification OTP."""
    import time
    start = time.monotonic()
    known_ids = set()

    # Collect pre-existing message IDs
    msgs = await fetch_messages(email)
    if msgs:
        for m in msgs:
            known_ids.add(m.get("id", ""))

    while time.monotonic() - start < cfg.verify_poll_timeout:
        msgs = await fetch_messages(email)
        if msgs:
            for m in msgs:
                mid = m.get("id", "")
                if mid in known_ids:
                    continue
                known_ids.add(mid)

                subject = m.get("subject", "")
                sender = m.get("from", "")
                # Check if this looks like a verification email
                combined = f"{subject} {sender}".lower()
                if any(kw in combined for kw in ["blackbox", "verification", "verify", "code", "confirm"]):
                    # Fetch full message to extract code
                    body = m.get("body", "") or m.get("text", "") or ""
                    if not body:
                        # Try to get body from message detail
                        try:
                            async with httpx.AsyncClient(timeout=15) as client:
                                resp = await client.get(f"https://api.catchmail.io/api/v1/message/{mid}?address={email}")
                                if resp.status_code == 200:
                                    detail = resp.json()
                                    body = detail.get("body", "") or detail.get("text", "") or ""
                        except:
                            pass

                    if body:
                        code = extract_otp_code(body)
                        if code:
                            return code

                    # Even from subject line
                    code = extract_otp_code(subject)
                    if code:
                        return code

        await asyncio.sleep(cfg.verify_poll_interval)

    return None

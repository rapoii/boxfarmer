"""Temporary mailbox client for catchmail.io.

No API key required — just pick a random address and poll for messages.
Ported from novaestellar/novabox with fixes for nodriver.
"""
from __future__ import annotations

import re
import secrets
import time

import httpx

from config import Config

_OTP_PATTERN = re.compile(r"\b(\d{6})\b")


def generate_email(domain: str = "catchmail.io") -> str:
    """Generate a random disposable address."""
    return f"{secrets.token_hex(6)}@{domain}"


async def fetch_messages(email: str, *, timeout: int = 30) -> list[dict]:
    """Return the message list for a mailbox, or [] on any API failure."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            "https://api.catchmail.io/api/v1/mailbox",
            params={"address": email},
        )
        if resp.status_code >= 400:
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("messages", "emails", "data", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []


async def read_message(message_id: str, email: str, *, timeout: int = 30) -> dict:
    """Fetch a single message body (needed to find the OTP)."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            f"https://api.catchmail.io/api/v1/message/{message_id}",
            params={"mailbox": email},
        )
        if resp.status_code >= 400:
            return {}
        data = resp.json()
        return data if isinstance(data, dict) else {}


def extract_otp(full_message: dict) -> str | None:
    """Pull the 6-digit code from the email body only.

    The mailbox list headers (id, date, size) contain their own 6-digit runs
    (e.g. the message-id timestamp) that would cause false matches — the OTP
    lives in the message's body, never anywhere else.
    """
    body = full_message.get("body")
    if not isinstance(body, dict):
        return None
    for key in ("text", "html"):
        value = body.get(key)
        if isinstance(value, str):
            match = _OTP_PATTERN.search(value)
            if match:
                return match.group(1)
    return None


async def wait_for_otp(email: str, cfg: Config) -> str | None:
    """Poll catchmail.io until a 6-digit OTP arrives or the timeout elapses.

    Returns the code, or None on timeout.
    """
    deadline = time.monotonic() + cfg.verify_poll_timeout

    while True:
        messages = await fetch_messages(email, timeout=cfg.request_timeout)
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get("id") or msg.get("_id") or msg.get("message_id")
            if msg_id is None:
                continue
            full = await read_message(str(msg_id), email, timeout=cfg.request_timeout)
            code = extract_otp(full)
            if code:
                return code

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        await _sleep(min(cfg.verify_poll_interval, remaining))


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(max(0.1, seconds))

"""Blackbox.ai client using nodriver (undetected-chromedriver based).

nodriver handles anti-detection natively. We just need to:
1. Open signup page
2. Fill form
3. Wait for OTP (via catchmail.io)
4. Verify OTP
5. Create API key
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import nodriver as uc

from anti_detect import AntiDetect
from config import Config


@dataclass
class AccountResult:
    """Result of a single account registration."""
    email: str = ""
    password: str = ""
    api_key: str = ""
    success: bool = False
    error: str = ""
    elapsed: float = 0.0


class BlackboxError(Exception):
    pass


class BlackboxClient:
    """Blackbox.ai registration + key creation via nodriver."""

    def __init__(self, cfg: Config, anti_detect: Optional[AntiDetect] = None):
        self._cfg = cfg
        self._anti_detect = anti_detect or AntiDetect(debug=False)
        self._browser: Optional[uc.Browser] = None
        self._tab: Optional[uc.Tab] = None

    async def start(self):
        """Launch browser with nodriver."""
        config = uc.Config()
        if self._cfg.headless:
            config.headless = True
        
        # Extra Chrome args for stability
        config.add_argument("--disable-blink-features=AutomationControlled")
        config.add_argument("--no-first-run")
        config.add_argument("--no-default-browser-check")
        config.add_argument("--disable-popup-blocking")
        
        self._browser = await uc.start(config)
        self._tab = await self._browser.get(f"{self._cfg.blackbox_url}/signup")
        
        # Inject anti-detect JS
        init_script = self._anti_detect.get_init_script()
        await self._tab.evaluate(init_script)
        tz_script = self._anti_detect.get_timezone_script()
        await self._tab.evaluate(tz_script)
        print(f"  [antidetect] Fingerprint injected ({len(init_script)} chars)")

    async def stop(self):
        """Stop browser."""
        if self._browser:
            try:
                self._browser.stop()
            except:
                pass

    @property
    def tab(self) -> uc.Tab:
        if not self._tab:
            raise BlackboxError("Client not started")
        return self._tab

    async def signup(self, email: str, password: str) -> None:
        """Fill signup form and submit."""
        tab = self.tab
        
        # Navigate to signup
        await tab.get(f"{self._cfg.blackbox_url}/signup")
        await tab.sleep(2)
        
        # Inject anti-detect again after navigation
        await tab.evaluate(self._anti_detect.get_init_script())
        
        # Fill email
        email_input = await tab.select('input[type="email"]', timeout=30)
        await email_input.clear_input()
        await email_input.send_keys(email)
        
        # Fill password
        pass_input = await tab.select('input[type="password"]', timeout=10)
        await pass_input.clear_input()
        await pass_input.send_keys(password)
        
        # Submit
        submit_btn = await tab.select('button[type="submit"]', timeout=10)
        await submit_btn.click()
        
        # Wait for OTP verification screen
        await tab.sleep(3)
        # Check if we're on verify page
        try:
            await tab.wait_for(text="Verify", timeout=15)
        except:
            try:
                await tab.wait_for(text="VERIFY", timeout=5)
            except:
                try:
                    await tab.select('input[maxlength="6"]', timeout=5)
                except:
                    raise BlackboxError("Did not reach OTP verification screen")

    async def verify_otp(self, code: str) -> None:
        """Enter OTP code and verify."""
        tab = self.tab
        
        # Find OTP input fields
        inputs = await tab.select_all('input[maxlength="1"]', timeout=10)
        
        if inputs and len(inputs) >= 6:
            # Individual digit inputs
            for i, digit in enumerate(code[:6]):
                await inputs[i].clear_input()
                await inputs[i].send_keys(digit)
                await tab.sleep(0.1)
        else:
            # Single input field
            try:
                otp_input = await tab.select('input[maxlength="6"]', timeout=5)
                await otp_input.clear_input()
                await otp_input.send_keys(code)
            except:
                # Try any visible input
                otp_input = await tab.select('input[type="text"]', timeout=5)
                await otp_input.clear_input()
                await otp_input.send_keys(code)
        
        await tab.sleep(1)
        
        # Click verify button
        try:
            verify_btn = await tab.find("VERIFY EMAIL", timeout=5)
            await verify_btn.click()
        except:
            try:
                verify_btn = await tab.find("Verify", timeout=3)
                await verify_btn.click()
            except:
                verify_btn = await tab.select('button[type="submit"]', timeout=5)
                await verify_btn.click()
        
        # Wait for redirect to /activity
        for _ in range(30):
            await tab.sleep(1)
            current_url = tab.url or ""
            if "/activity" in current_url:
                return
        
        # Check if we're still on signup (verify failed)
        current_url = tab.url or ""
        if "/signup" in current_url or "/auth" in current_url:
            raise BlackboxError(f"OTP verify failed — still at {current_url}")

    async def create_api_key(self, key_name: str = "auto-farm-key") -> str:
        """Navigate to API keys page and create a new key."""
        tab = self.tab
        
        # Go to API keys page
        await tab.get(f"{self._cfg.blackbox_url}/api-keys")
        await tab.sleep(3)
        
        # Inject anti-detect
        await tab.evaluate(self._anti_detect.get_init_script())
        
        # Look for "Create new key" / "Generate" button
        try:
            create_btn = await tab.find("Create", timeout=10)
            await create_btn.click()
        except:
            try:
                create_btn = await tab.find("Generate", timeout=5)
                await create_btn.click()
            except:
                create_btn = await tab.find("New Key", timeout=5)
                await create_btn.click()
        
        await tab.sleep(2)
        
        # If there's a name input, fill it
        try:
            name_input = await tab.select('input[placeholder*="name"], input[placeholder*="Name"]', timeout=3)
            await name_input.clear_input()
            await name_input.send_keys(key_name)
        except:
            pass
        
        # Submit/confirm key creation
        try:
            confirm_btn = await tab.find("Create", timeout=5)
            await confirm_btn.click()
        except:
            try:
                confirm_btn = await tab.find("Generate", timeout=3)
                await confirm_btn.click()
            except:
                confirm_btn = await tab.select('button[type="submit"]', timeout=5)
                await confirm_btn.click()
        
        await tab.sleep(3)
        
        # Extract API key from page
        page_content = await tab.get_content()
        if page_content:
            # Look for sk-xxx pattern
            api_keys = re.findall(r'(sk-[A-Za-z0-9_\-]{20,})', str(page_content))
            if api_keys:
                return api_keys[0]
            
            # Look for any key in input value or text
            key_elements = await tab.select_all('input[value*="sk-"]', timeout=3)
            if key_elements:
                val = await key_elements[0].get_js_attributes()
                if val and "value" in val:
                    key = val["value"]
                    if key.startswith("sk-"):
                        return key
        
        raise BlackboxError("API key not found after creation")

    async def register_account(self, email: str, password: str) -> AccountResult:
        """Full registration flow: signup → OTP → verify → create key."""
        result = AccountResult(email=email, password=password)
        start = time.monotonic()
        
        try:
            print(f"    Signup...")
            await self.signup(email, password)
            
            print(f"    Waiting for OTP...")
            from providers.tempmail import wait_for_otp
            code = await wait_for_otp(email, self._cfg)
            if not code:
                raise BlackboxError(f"OTP not received within {self._cfg.verify_poll_timeout}s")
            
            print(f"    OTP: {code}, verifying...")
            await self.verify_otp(code)
            
            print(f"    Creating API key...")
            api_key = await self.create_api_key(self._cfg.key_name)
            
            result.api_key = api_key
            result.success = True
            print(f"    API key: {api_key[:25]}...")
            
        except Exception as e:
            result.error = str(e)[:200]
            print(f"    FAILED: {result.error}")
        
        result.elapsed = time.monotonic() - start
        return result

"""Blackbox.ai client using nodriver (undetected-chromedriver based).

nodriver handles anti-detection natively. We just need to:
1. Open signup page
2. Fill form
3. Wait for OTP (via catchmail.io or generator.email)
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
        config.add_argument("--no-first-run")
        config.add_argument("--no-default-browser-check")
        config.add_argument("--disable-popup-blocking")
        config.add_argument("--disable-gpu")

        self._browser = await uc.start(config)
        self._tab = await self._browser.get(f"{self._cfg.blackbox_url}/signup")
        await self._tab.sleep(3)
        await self._inject_antidetect()

    async def _inject_antidetect(self):
        """Inject anti-detect JS into current tab."""
        if not self._tab:
            return
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

    async def _get_inputs(self):
        """Get all input elements on page."""
        inputs = await self.tab.select_all("input", timeout=10)
        if not inputs:
            raise BlackboxError("No input fields found on page")
        return inputs

    async def signup(self, email: str, password: str) -> None:
        """Fill signup form and submit."""
        tab = self.tab
        await tab.get(f"{self._cfg.blackbox_url}/signup")
        await tab.sleep(5)
        await self._inject_antidetect()

        print(f"    URL: {tab.url}")

        inputs = await self._get_inputs()
        if len(inputs) < 2:
            raise BlackboxError(f"Expected 2+ inputs, got {len(inputs)}")

        await inputs[0].clear_input()
        await inputs[0].send_keys(email)
        print(f"    Email filled: {email}")

        await inputs[1].clear_input()
        await inputs[1].send_keys(password)
        print(f"    Password filled")

        # Click submit
        try:
            submit = await tab.select('button[type="submit"]', timeout=5)
            if submit:
                await submit.click()
        except:
            await tab.evaluate('document.querySelector("button[type=\\"submit\\"]").click()')
        print(f"    Submit clicked, waiting for OTP screen...")

        # Wait for OTP screen
        await tab.sleep(3)
        found = False
        for text_try in ["Verify", "VERIFY", "Verification", "code"]:
            try:
                await tab.find(text_try, timeout=8)
                found = True
                print(f"    Found '{text_try}' — OTP screen reached")
                break
            except:
                continue

        if not found:
            url = tab.url or ""
            if "/activity" in url:
                print(f"    Auto-verified! On activity page")
                return
            raise BlackboxError(f"Did not reach OTP screen (url: {tab.url})")

    async def verify_otp(self, code: str) -> None:
        """Enter OTP code and verify."""
        tab = self.tab
        print(f"    Entering OTP: {code}")

        # Get all inputs and find the OTP field(s)
        all_inputs = await tab.select_all("input", timeout=5)

        # Check for 6 individual digit inputs (maxLength=1)
        otp_inputs = []
        regular_inputs = []
        for inp in all_inputs:
            try:
                html = await tab.evaluate(
                    '(function() { var r = []; var els = document.querySelectorAll("input"); '
                    'for(var i=0;i<els.length;i++) { r.push(els[i].maxLength); } return r.join(","); })()'
                )
                maxlens = [int(x) for x in html.split(",") if x.strip() != "-1"]
                break
            except:
                maxlens = []
                break

        # Try to find maxLength=1 inputs via CSS
        try:
            count_1 = await tab.evaluate('document.querySelectorAll("input[maxlength=\\"1\\"]").length')
        except:
            count_1 = 0

        if count_1 and int(count_1) >= 6:
            # Individual digit inputs
            print(f"    Found {count_1} individual digit inputs")
            for i in range(6):
                try:
                    el = await tab.select(f'input[maxlength="1"]', timeout=2)
                    # nth-of-type won't work well, use JS
                    await tab.evaluate(
                        f'(function() {{ var els = document.querySelectorAll("input[maxlength=\\"1\\"]"); '
                        f'els[{i}].focus(); els[{i}].value = "{code[i]}"; '
                        f'els[{i}].dispatchEvent(new Event("input", {{bubbles:true}})); }})()'
                    )
                except:
                    pass
            print(f"    OTP entered (individual inputs)")
            await tab.sleep(1)
            await self._click_verify()
            await self._wait_for_activity()
            return

        # Single OTP input field
        # Try to find a text/email input that's not email or password
        target = None
        for inp in all_inputs:
            try:
                el_type = await tab.evaluate(
                    '(function() { var els = document.querySelectorAll("input"); '
                    'for(var i=0;i<els.length;i++) { '
                    '  if(els[i].type !== "email" && els[i].type !== "password" && els[i].type !== "hidden") '
                    '    return els[i].type + "|" + els[i].name + "|" + els[i].maxLength; '
                    '} return "none"; })()'
                )
                if el_type and el_type != "none":
                    target = inp
                    break
            except:
                pass

        if not target and all_inputs:
            # Just use the first non-password input
            for inp in all_inputs:
                target = inp
                break

        if target:
            await target.clear_input()
            await target.send_keys(code)
            print(f"    OTP entered (single input)")
        else:
            # Last resort: JS injection
            await tab.evaluate(
                f'(function() {{ var els = document.querySelectorAll("input"); '
                f'for(var i=0;i<els.length;i++) {{ '
                f'  if(els[i].type !== "password" && els[i].type !== "hidden") {{ '
                f'    els[i].value = "{code}"; '
                f'    els[i].dispatchEvent(new Event("input", {{bubbles:true}})); break; '
                f'  }}' '\n'
                f'}} }})()'
            )
            print(f"    OTP entered (JS fallback)")

        await tab.sleep(1)
        await self._click_verify()
        await self._wait_for_activity()

    async def _click_verify(self):
        """Click verify button."""
        tab = self.tab
        for text in ["VERIFY EMAIL", "Verify Email", "Verify", "VERIFY"]:
            try:
                el = await tab.find(text, timeout=3)
                if el:
                    await el.click()
                    print(f"    Clicked '{text}'")
                    return
            except:
                continue
        # Fallback: submit
        try:
            await tab.evaluate('document.querySelector("button[type=\\"submit\\"]").click()')
            print(f"    Clicked submit (fallback)")
        except:
            pass

    async def _wait_for_activity(self):
        """Wait for redirect to /activity page."""
        tab = self.tab
        for i in range(30):
            await tab.sleep(1)
            url = tab.url or ""
            if "/activity" in url:
                print(f"    Verified! -> /activity")
                return
            if i % 5 == 0:
                print(f"    Waiting... ({url[:60]})")
        url = tab.url or ""
        if "/signup" in url or "/auth" in url:
            raise BlackboxError(f"OTP verify failed — still at {url}")
        print(f"    After verify: {url}")

    async def create_api_key(self, key_name: str = "auto-farm-key") -> str:
        """Navigate to API keys page and create a new key."""
        tab = self.tab

        # Navigate to keys page (CORRECT URL: /keys, not /api-keys)
        await tab.get(f"{self._cfg.blackbox_url}/keys")
        await tab.sleep(5)
        await self._inject_antidetect()

        current_url = tab.url or ""
        print(f"    Keys page: {current_url}")

        # Check if logged in
        if "/auth" in current_url or "/login" in current_url:
            raise BlackboxError(f"Not logged in — redirected to {current_url}")

        # Wait for CREATE KEY button
        clicked = False
        for text in ["CREATE KEY", "Create Key", "Create key", "Create", "Generate"]:
            try:
                el = await tab.find(text, timeout=8)
                if el:
                    await el.click()
                    clicked = True
                    print(f"    Clicked '{text}'")
                    break
            except:
                continue

        if not clicked:
            raise BlackboxError("CREATE KEY button not found")

        await tab.sleep(3)

        # Modal appears — fill key name
        try:
            inputs = await tab.select_all("input", timeout=5)
            if inputs:
                for inp in inputs:
                    await inp.clear_input()
                    await inp.send_keys(key_name)
                    print(f"    Key name filled: {key_name}")
                    break
        except:
            pass

        await tab.sleep(1)

        # Click "Create API Key" confirm button
        for text in ["CREATE API KEY", "Create API Key", "Create API key", "Create", "Submit", "Confirm"]:
            try:
                el = await tab.find(text, timeout=5)
                if el:
                    # Wait for button to become enabled (not disabled)
                    await tab.sleep(1)
                    await el.click()
                    print(f"    Confirmed: '{text}'")
                    break
            except:
                continue

        await tab.sleep(5)

        # === Extract API key from page ===
        all_text = await tab.evaluate("document.body.innerText") or ""

        # Method 1: sk- pattern in page text
        api_keys = re.findall(r'(sk-[A-Za-z0-9_\-]{20,})', all_text)
        if api_keys:
            return api_keys[0]

        # Method 2: Look in input values
        try:
            val = await tab.evaluate(
                '(function() { var els = document.querySelectorAll("input"); '
                'for(var i=0;i<els.length;i++) { '
                '  if(els[i].value && els[i].value.indexOf("sk-") >= 0) return els[i].value; '
                '} return ""; })()'
            )
            if val and val.startswith("sk-"):
                return val
        except:
            pass

        # Method 3: code/pre elements
        try:
            code_text = await tab.evaluate(
                '(function() { var els = document.querySelectorAll("code, pre, [class*=key], [class*=token]"); '
                'var r = []; for(var i=0;i<els.length;i++) r.push(els[i].innerText); return r.join("|"); })()'
            )
            if code_text and "sk-" in code_text:
                api_keys = re.findall(r'(sk-[A-Za-z0-9_\-]{20,})', code_text)
                if api_keys:
                    return api_keys[0]
        except:
            pass

        # Debug
        print(f"    [DEBUG] Page text: {all_text[:500]}")

        raise BlackboxError("API key not found after creation")

    async def register_account(self, email: str, password: str) -> AccountResult:
        """Full registration flow: signup → OTP → verify → create key."""
        result = AccountResult(email=email, password=password)
        start = time.monotonic()

        try:
            print(f"    Signup...")
            await self.signup(email, password)

            print(f"    Waiting for OTP...")
            code = None

            if self._cfg.email_mode == "generator":
                # generator.email mode — open in a browser tab
                from providers.generator_email import GeneratorEmailClient
                gen = GeneratorEmailClient(self._browser)
                # We already have the email from signup, so just open inbox
                gen._email = email.split("@")[0]
                gen._domain = email.split("@")[1]
                gen._tab = await self._browser.get(
                    f"https://generator.email/{gen._domain}/{gen._email}"
                )
                await gen._tab.sleep(3)
                code = await gen.wait_for_otp(self._cfg)
                await gen.close()
            else:
                # catchmail.io mode — API-based
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

"""Blackbox.ai client using nodriver (undetected-chromedriver based).

nodriver handles anti-detection natively. We just need to:
1. Open signup page
2. Fill form (React inputs need nativeSet pattern)
3. Wait for OTP (via catchmail.io or generator.email)
4. Verify OTP (#verification-code input)
5. Create API key (dialog-based flow)

Key findings (verified via MCP Playwright):
- Signup inputs: #email-password-signup, #password-signup
- OTP input: #verification-code (maxLength=6)
- Buttons: "CREATE ACCOUNT", "Verify Email", "Create key", "Create API Key"
- React inputs REQUIRE nativeSet pattern (HTMLInputElement.prototype.value.set)
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
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
            except Exception:
                pass

    @property
    def tab(self) -> uc.Tab:
        if not self._tab:
            raise BlackboxError("Client not started")
        return self._tab

    async def _fill_react_input(self, selector: str, value: str, tab: Optional[uc.Tab] = None) -> bool:
        """Fill a React-controlled input using nativeSet pattern."""
        use_tab = tab or self.tab
        js = (
            '(function() { '
            f'  var el = document.querySelector("{selector}"); '
            '  if (!el) return false; '
            '  var nativeSet = Object.getOwnPropertyDescriptor('
            '    window.HTMLInputElement.prototype, "value").set; '
            f'  nativeSet.call(el, {repr(value)}); '
            '  el.dispatchEvent(new Event("input", {bubbles: true})); '
            '  el.dispatchEvent(new Event("change", {bubbles: true})); '
            f'  return el.value === {repr(value)}; '
            '})()'
        )
        result = await use_tab.evaluate(js)
        return bool(result)

    async def signup(self, email: str, password: str, tab: Optional[uc.Tab] = None) -> None:
        """Fill signup form and submit.

        Uses #email-password-signup and #password-signup selectors
        with nativeSet pattern for React inputs.
        """
        use_tab = tab or self.tab
        await use_tab.get(f"{self._cfg.blackbox_url}/signup")
        await use_tab.sleep(5)
        # Inject antidetect on this tab
        init_script = self._anti_detect.get_init_script()
        await use_tab.evaluate(init_script)
        tz_script = self._anti_detect.get_timezone_script()
        await use_tab.evaluate(tz_script)

        print(f"    URL: {use_tab.url}")

        # Fill email (React input)
        ok = await self._fill_react_input("#email-password-signup", email, tab=use_tab)
        if not ok:
            ok = await self._fill_react_input('input[type="email"]', email, tab=use_tab)
        if not ok:
            raise BlackboxError("Email input not found")
        print(f"    Email filled: {email}")

        # Fill password (React input)
        ok = await self._fill_react_input("#password-signup", password, tab=use_tab)
        if not ok:
            ok = await self._fill_react_input('input[type="password"]', password, tab=use_tab)
        if not ok:
            raise BlackboxError("Password input not found")
        print(f"    Password filled")

        # Click "CREATE ACCOUNT" button
        clicked = False
        for text in ["CREATE ACCOUNT", "Create Account", "Create account"]:
            try:
                el = await use_tab.find(text, timeout=3)
                if el:
                    await el.click()
                    clicked = True
                    print(f"    Clicked '{text}'")
                    break
            except Exception:
                continue

        if not clicked:
            await use_tab.evaluate(
                '(function() { '
                '  var btns = document.querySelectorAll("button"); '
                '  for (var i = 0; i < btns.length; i++) { '
                '    if (btns[i].textContent.trim().toUpperCase().indexOf("CREATE") >= 0 && '
                '        btns[i].textContent.trim().toUpperCase().indexOf("ACCOUNT") >= 0) { '
                '      btns[i].click(); return true; '
                '    } '
                '  } '
                '  return false; '
                '})()'
            )
            print(f"    Clicked CREATE ACCOUNT (JS fallback)")

        # Wait for OTP screen
        await use_tab.sleep(3)
        found = False
        for text_try in ["Verify Email", "Verify", "VERIFY", "Verification", "code"]:
            try:
                await use_tab.find(text_try, timeout=8)
                found = True
                print(f"    Found '{text_try}' — OTP screen reached")
                break
            except Exception:
                continue

        if not found:
            url = use_tab.url or ""
            if "/activity" in url:
                print(f"    Auto-verified! On activity page")
                return
            raise BlackboxError(f"Did not reach OTP screen (url: {use_tab.url})")

    async def verify_otp(self, code: str, tab: Optional[uc.Tab] = None) -> None:
        """Enter OTP code and verify."""
        use_tab = tab or self.tab
        print(f"    Entering OTP: {code}")

        # #verification-code input (React, needs nativeSet)
        ok = await self._fill_react_input("#verification-code", code, tab=use_tab)
        if ok:
            print(f"    OTP entered via #verification-code")
        else:
            # maxLength=6 text input
            ok = await self._fill_react_input(
                'input[type="text"][maxlength="6"]', code, tab=use_tab
            )
            if ok:
                print(f"    OTP entered via maxLength=6 input")
            else:
                # Generic fallback
                js = (
                    '(function() { '
                    '  var els = document.querySelectorAll("input"); '
                    '  var nativeSet = Object.getOwnPropertyDescriptor('
                    '    window.HTMLInputElement.prototype, "value").set; '
                    '  for (var i = 0; i < els.length; i++) { '
                    '    if (els[i].type !== "email" && els[i].type !== "password" && '
                    '        els[i].type !== "hidden") { '
                    f'      nativeSet.call(els[i], {repr(code)}); '
                    '      els[i].dispatchEvent(new Event("input", {bubbles: true})); '
                    '      els[i].dispatchEvent(new Event("change", {bubbles: true})); '
                    '      return els[i].id || els[i].name || els[i].type; '
                    '    } '
                    '  } '
                    '  return false; '
                    '})()'
                )
                fallback = await use_tab.evaluate(js)
                if fallback:
                    print(f"    OTP entered via generic input ({fallback})")
                else:
                    raise BlackboxError("OTP input not found")

        await use_tab.sleep(1)
        await self._click_verify(use_tab)
        await self._wait_for_activity(use_tab)

    async def _click_verify(self, tab: Optional[uc.Tab] = None):
        """Click verify button."""
        use_tab = tab or self.tab
        for text in ["Verify Email", "VERIFY EMAIL", "Verify", "VERIFY"]:
            try:
                el = await use_tab.find(text, timeout=3)
                if el:
                    await el.click()
                    print(f"    Clicked '{text}'")
                    return
            except Exception:
                continue
        # Fallback: JS click
        await use_tab.evaluate(
            '(function() { '
            '  var btns = document.querySelectorAll("button"); '
            '  for (var i = 0; i < btns.length; i++) { '
            '    if (btns[i].textContent.trim().toLowerCase().indexOf("verify") >= 0) { '
            '      btns[i].click(); return true; '
            '    } '
            '  } '
            '  return false; '
            '})()'
        )
        print(f"    Clicked verify (JS fallback)")

    async def _wait_for_activity(self, tab: Optional[uc.Tab] = None):
        """Wait for redirect to /activity page."""
        use_tab = tab or self.tab
        for i in range(30):
            await use_tab.sleep(1)
            url = use_tab.url or ""
            if "/activity" in url:
                print(f"    Verified! -> /activity")
                return
            if i % 5 == 0:
                print(f"    Waiting... ({url[:60]})")
        url = use_tab.url or ""
        if "/signup" in url or "/auth" in url:
            raise BlackboxError(f"OTP verify failed — still at {url}")
        print(f"    After verify: {url}")

    async def create_api_key(self, key_name: str = "auto-farm-key", tab: Optional[uc.Tab] = None) -> str:
        """Navigate to API keys page and create a new key."""
        use_tab = tab or self.tab

        await use_tab.get(f"{self._cfg.blackbox_url}/keys")
        await use_tab.sleep(5)
        await self._inject_antidetect()

        current_url = use_tab.url or ""
        print(f"    Keys page: {current_url}")

        if "/auth" in current_url or "/login" in current_url:
            raise BlackboxError(f"Not logged in — redirected to {current_url}")

        # Click "Create key" button
        clicked = False
        for text in ["Create key", "CREATE KEY", "Create Key"]:
            try:
                el = await use_tab.find(text, timeout=8)
                if el:
                    await el.click()
                    clicked = True
                    print(f"    Clicked '{text}'")
                    break
            except Exception:
                continue

        if not clicked:
            raise BlackboxError("CREATE KEY button not found")

        await use_tab.sleep(2)

        # Fill key name — MUST use send_keys() for real CDP keyboard events.
        # React ignores nativeSet, execCommand, and JS-dispatched KeyboardEvents.
        # send_keys() goes through Input.dispatchKeyEvent → triggers React onChange → button enables.
        unique_name = f"{key_name}-{int(time.time())}"

        # Find and click the name input to focus it
        try:
            inp = await use_tab.select('input[placeholder*="e.g."]', timeout=3)
            if inp:
                await inp.click()
                await use_tab.sleep(0.5)
                await inp.send_keys(unique_name)
                await use_tab.sleep(1)
                print(f"    Key name filled via send_keys: {unique_name}")
            else:
                raise BlackboxError("Name input not found in dialog")
        except Exception as e:
            if isinstance(e, BlackboxError):
                raise
            # Fallback: try finding input inside dialog
            try:
                dialog = await use_tab.select("[role=dialog], dialog", timeout=2)
                if dialog:
                    inp2 = await use_tab.select("input", timeout=2)
                    if inp2:
                        await inp2.click()
                        await use_tab.sleep(0.5)
                        await inp2.send_keys(unique_name)
                        await use_tab.sleep(1)
                        print(f"    Key name filled via dialog fallback: {unique_name}")
                    else:
                        raise BlackboxError("No input found in dialog")
                else:
                    raise BlackboxError("Dialog not found")
            except Exception as e2:
                if isinstance(e2, BlackboxError):
                    raise
                raise BlackboxError(f"Cannot fill key name: {e2}")

        await use_tab.sleep(1)

        # Click "Create API Key" confirm button
        for text in ["Create API Key", "CREATE API KEY", "Create API key"]:
            try:
                el = await use_tab.find(text, timeout=5)
                if el:
                    await el.click()
                    print(f"    Confirmed: '{text}'")
                    break
            except Exception:
                continue

        await use_tab.sleep(5)

        # Extract API key from page
        all_text = await use_tab.evaluate("document.body.innerText") or ""

        # Method 1: sk- pattern in page text
        api_keys = re.findall(r'(sk-[A-Za-z0-9_\-]{20,})', all_text)
        if api_keys:
            return api_keys[0]

        # Method 2: Look in input values
        try:
            val = await use_tab.evaluate(
                '(function() { var els = document.querySelectorAll("input"); '
                'for(var i=0;i<els.length;i++) { '
                '  if(els[i].value && els[i].value.indexOf("sk-") >= 0) return els[i].value; '
                '} return ""; })()'
            )
            if val and val.startswith("sk-"):
                return val
        except Exception:
            pass

        print(f"    [DEBUG] Page text: {all_text[:500]}")
        raise BlackboxError("API key not found after creation")

    async def register_account(self, email: str, password: str) -> AccountResult:
        """Full registration flow.

        Catchmail: signup → wait OTP (HTTP API) → verify → create key
        Generator.email (proven flow from test_clean.py):
          1. Navigate inbox tab to blackbox via signup() → on OTP screen
          2. Open NEW TAB for inbox check → get OTP (must be fresh, old tabs stale)
          3. Navigate NEW TAB to blackbox → enter OTP → verify → create key
          (uses new_tab for steps 2+3 — avoids stale Tab 0 issues)
        """
        result = AccountResult(email=email, password=password)
        start = time.monotonic()

        try:
            if self._cfg.email_mode == "generator":
                # Step 1: Navigate inbox tab to blackbox
                print(f"    Signup (inbox tab → blackbox)...")
                await self.signup(email, password, tab=self._tab)

                # Step 2: Open NEW TAB for inbox check (fresh, no stale data)
                print(f"    Checking inbox for OTP (new tab)...")
                from providers.generator_email import GeneratorEmailClient
                gen = GeneratorEmailClient(self._browser)
                gen._email = email.split("@")[0]
                gen._domain = email.split("@")[1]
                code = await gen.wait_for_otp_new_tab(self._cfg)

                if not code:
                    raise BlackboxError(
                        f"OTP not received within {self._cfg.verify_poll_timeout}s"
                    )

                # Step 3: Navigate the NEW TAB (which has inbox) to blackbox for OTP entry
                print(f"    OTP: {code}, navigating to blackbox...")
                otp_tab = gen._tab  # the fresh inbox tab
                await otp_tab.get(f"{self._cfg.blackbox_url}/signup")
                await otp_tab.sleep(3)

                print(f"    Entering OTP...")
                await self.verify_otp(code, tab=otp_tab)

                print(f"    Creating API key...")
                api_key = await self.create_api_key(self._cfg.key_name, tab=otp_tab)

            else:
                print(f"    Signup...")
                await self.signup(email, password)

                print(f"    Waiting for OTP...")
                from providers.tempmail import wait_for_otp
                code = await wait_for_otp(email, self._cfg)

                if not code:
                    raise BlackboxError(
                        f"OTP not received within {self._cfg.verify_poll_timeout}s"
                    )

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

"""Test single account registration — full log.

Usage:
  python test_e2e.py              # catchmail (default)
  python test_e2e.py catchmail    # same
  python test_e2e.py generator    # generator.email mode
"""
import asyncio
import os
import sys
import time
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from anti_detect import AntiDetect
from injector import inject_key, count_blackbox


async def test():
    email_mode = sys.argv[1] if len(sys.argv) > 1 else "catchmail"

    print("=" * 60)
    print(f"BOXFARMER — E2E TEST (single account)")
    print(f"Email mode: {email_mode}")
    print("=" * 60)
    print()

    # [1/5] AntiDetect
    print("[1/5] AntiDetect init...")
    ad = AntiDetect(debug=False)
    print(f"  [antidetect] Session: {ad.session_id}")
    print(f"  [antidetect] GPU: {ad.profile['vendor']} {ad.profile['renderer']}")
    print(f"  [antidetect] Platform: {ad.profile['platform']}, Cores: {ad.profile['cores']}, RAM: {ad.profile['ram']}GB")
    print(f"  [antidetect] TZ: {ad.profile['tz']}, Locale: {ad.profile['locale']}")
    print(f"  [antidetect] Screen: {ad.profile['screen_w']}x{ad.profile['screen_h']}, DPR: {ad.profile['dpr']}")
    print()

    # [2/5] Config
    print("[2/5] Config...")
    cfg = Config(headless=True, email_mode=email_mode)
    print(f"  ✓ headless={cfg.headless}")
    print(f"  ✓ email_mode={cfg.email_mode}")
    print()

    # [3/5] Generate email
    print("[3/5] Generate email...")
    if email_mode == "generator":
        from providers.generator_email import GeneratorEmailClient
        from providers.blackbox import BlackboxClient
        # Need browser first to get email
        tmp_client = BlackboxClient(cfg, anti_detect=ad)
        await tmp_client.start()
        gen = GeneratorEmailClient(tmp_client._browser)
        email = await gen.open()
        password = "BoxfarmerTest2026!"
        await gen.close()
        print(f"  ✓ Email: {email}")
        print()
        print("[4/5] Register account (nodriver)...")
        result = await tmp_client.register_account(email, password)
        await tmp_client.stop()
    else:
        from providers.tempmail import generate_email
        email = generate_email(cfg.tempmail_domain)
        password = "BoxfarmerTest2026!"
        print(f"  ✓ Email: {email}")
        print()
        print("[4/5] Register account (nodriver)...")
        from providers.blackbox import BlackboxClient
        client = BlackboxClient(cfg, anti_detect=ad)
        await client.start()
        result = await client.register_account(email, password)
        await client.stop()
    print()

    if not result.success:
        print("=" * 60)
        print("FAILED!")
        print("=" * 60)
        print(f"  Email: {email}")
        print(f"  Error: {result.error}")
        print("=" * 60)
        return

    # [5/5] Inject to 9Router
    print("[5/5] Inject to 9Router...")
    try:
        conn_id = inject_key(email, result.api_key)
        total = count_blackbox()
        print(f"  ✓ Connection: {conn_id}")
        print(f"  ✓ Total in 9Router: {total}")
    except Exception as e:
        print(f"  ✗ Inject failed: {e}")

    print()
    print("=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print(f"  Email:    {email}")
    print(f"  Password: {password}")
    print(f"  API Key:  {result.api_key[:25]}...")
    print(f"  Time:     {result.elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test())

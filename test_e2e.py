"""Test single account registration — full log.

Usage:
  python test_e2e.py              # catchmail (default)
  python test_e2e.py catchmail    # same
  python test_e2e.py generator    # generator.email mode
"""
import asyncio
import os
import sys

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
    print(f"  [antidetect] GPU: {ad.vendor} {ad.renderer}")
    print(f"  [antidetect] Platform: {ad.platform}, Cores: {ad.cores}, RAM: {ad.memory}GB")
    print(f"  [antidetect] TZ: {ad.timezone}, Locale: {ad.locale}")
    print(f"  [antidetect] Screen: {ad.screen_w}x{ad.screen_h}, DPR: {ad.dpr}")
    print()

    # [2/5] Config
    print("[2/5] Config...")
    cfg = Config(headless=True, email_mode=email_mode)
    print(f"  ✓ headless={cfg.headless}")
    print(f"  ✓ email_mode={cfg.email_mode}")
    print()

    from providers.blackbox import BlackboxClient

    # [3/5] Generate email
    print("[3/5] Generate email...")
    client = BlackboxClient(cfg, anti_detect=ad)
    await client.start()

    if email_mode == "generator":
        from providers.generator_email import GeneratorEmailClient
        gen = GeneratorEmailClient(client._browser)
        email = await gen.open(preferred_domain=cfg.generator_preferred_domain)
        # Set inbox tab as client's main tab — register_account will
        # navigate it to blackbox, then open fresh tab for OTP check
        client._tab = gen._tab
        password = "BoxfarmerTest2026!"
        print(f"  ✓ Email: {email}")
    else:
        from providers.tempmail import generate_email
        email = generate_email(cfg.tempmail_domain)
        password = "BoxfarmerTest2026!"
        print(f"  ✓ Email: {email}")
    print()

    # [4/5] Register account
    print("[4/5] Register account (nodriver)...")
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

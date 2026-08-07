"""Test single account registration — full log."""
import asyncio
import os
import time
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from anti_detect import AntiDetect
from injector import inject_key, count_blackbox
from providers.blackbox import BlackboxClient, AccountResult
from providers.tempmail import generate_email


async def test_single():
    print("=" * 60)
    print("BOXFARMER — E2E TEST (single account)")
    print("=" * 60)
    print()

    # Step 1: AntiDetect
    print("[1/5] AntiDetect init...")
    ad = AntiDetect(debug=True)
    print()

    # Step 2: Config
    print("[2/5] Config...")
    cfg = Config(max_workers=1, headless=True)
    print(f"  ✓ headless={cfg.headless}")
    print()

    # Step 3: Generate email
    print("[3/5] Generate email...")
    email = generate_email(cfg.tempmail_domain)
    password = "BoxfarmerTest2026!"
    print(f"  ✓ Email: {email}")
    print()

    # Step 4: Register
    print("[4/5] Register account (nodriver)...")
    client = BlackboxClient(cfg, anti_detect=ad)
    try:
        await client.start()
        result = await client.register_account(email, password)
    except Exception as e:
        traceback.print_exc()
        result = AccountResult(email=email, password=password, error=str(e)[:200])
    finally:
        await client.stop()

    print()

    if result.success:
        # Step 5: Inject to 9Router
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
        print(f"  API Key:  {result.api_key}")
        print(f"  Time:     {result.elapsed:.1f}s")
        print("=" * 60)
    else:
        print("=" * 60)
        print("FAILED!")
        print("=" * 60)
        print(f"  Email: {email}")
        print(f"  Error: {result.error}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_single())

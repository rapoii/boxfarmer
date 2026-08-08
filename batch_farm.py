"""Batch farm — register N accounts and inject to 9Router.

Batch-based concurrency:
  1. Random pick 1-3 accounts per batch
  2. Run them concurrently
  3. Wait for ALL to finish
  4. If more remain → random cooldown 10-20s
  5. Repeat until done

Usage:
  python batch_farm.py 20                     # 20 accounts, catchmail (default)
  python batch_farm.py 20 catchmail           # same
  python batch_farm.py 20 generator           # generator.email mode
"""
import asyncio
import os
import secrets
import string
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from anti_detect import AntiDetect
from injector import inject_key, count_blackbox
from providers.blackbox import BlackboxClient, AccountResult
from providers.tempmail import generate_email as gen_catchmail


def generate_password(length=16):
    return "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(length))


async def _farm_one(idx: int, cfg: Config, results: list):
    """Farm a single account."""
    ad = AntiDetect(debug=False)

    if cfg.email_mode == "generator":
        # For generator.email, we need a browser to get the email first
        from providers.generator_email import GeneratorEmailClient
        client = BlackboxClient(cfg, anti_detect=ad)
        try:
            await client.start()
            gen = GeneratorEmailClient(client._browser)
            email = await gen.open(preferred_domain=cfg.generator_preferred_domain)
            # Set inbox tab as main tab — register_account navigates it to blackbox
            client._tab = gen._tab
            password = generate_password()
            print(f"    [{idx:02d}] Starting: {email}")
            result = await client.register_account(email, password)
        except Exception as e:
            email = f"unknown-{idx}@generator.email"
            result = AccountResult(email=email, error=str(e)[:200])
        finally:
            try:
                await client.stop()
            except:
                pass
    else:
        # catchmail mode
        email = gen_catchmail(cfg.tempmail_domain)
        password = generate_password()

        print(f"    [{idx:02d}] Starting: {email}")
        client = BlackboxClient(cfg, anti_detect=ad)
        result = None
        try:
            await client.start()
            result = await client.register_account(email, password)
        except Exception as e:
            result = AccountResult(email=email, password=password, error=str(e)[:200])
        finally:
            try:
                await client.stop()
            except:
                pass

    results.append(result)

    if result.success:
        with open("output/keys.txt", "a", encoding="utf-8") as f:
            f.write(f"{email}:{password}:{result.api_key}\n")
        try:
            conn_id = inject_key(email, result.api_key)
            print(f"    [{idx:02d}] [OK] -> 9Router: {conn_id}")
        except Exception as e:
            print(f"    [{idx:02d}] [OK] (inject fail: {e})")
    else:
        print(f"    [{idx:02d}] [FAIL] {result.error[:60]}")

    return result


async def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    email_mode = sys.argv[2] if len(sys.argv) > 2 else "catchmail"

    print("=" * 60)
    print(f"BOXFARMER — BATCH FARM ({N} accounts)")
    print(f"Email mode:  {email_mode}")
    print(f"Concurrency: random 1-3 per batch")
    print(f"Cooldown:    random 10-20s between batches")
    print("=" * 60)
    print()

    current = count_blackbox()
    print(f"  Current 9Router blackbox: {current}")
    print()

    cfg = Config(headless=True, email_mode=email_mode)
    Path("output").mkdir(exist_ok=True)

    success = 0
    fail = 0
    results = []
    remaining = N
    batch_num = 0

    while remaining > 0:
        batch_num += 1
        # Random batch size: 1-3
        batch_size = secrets.randbelow(3) + 1
        if batch_size > remaining:
            batch_size = remaining

        print(f"  [BATCH {batch_num}] {batch_size} accounts (remaining: {remaining})")

        # Create tasks for this batch
        batch_tasks = []
        for i in range(batch_size):
            idx = N - remaining + i + 1
            batch_tasks.append(_farm_one(idx, cfg, results))

        # Run all in this batch concurrently
        await asyncio.gather(*batch_tasks, return_exceptions=True)

        # Count results from this batch
        for r in results[-batch_size:]:
            if r and r.success:
                success += 1
            else:
                fail += 1

        remaining -= batch_size

        # Progress update
        total_now = count_blackbox()
        print(f"  [PROGRESS] {success + fail}/{N} (OK:{success} FAIL:{fail}) | 9Router: {total_now}")

        # Cooldown if more remaining
        if remaining > 0:
            cooldown = secrets.randbelow(11) + 10  # 10-20s
            print(f"  [COOLDOWN] {cooldown}s...")
            await asyncio.sleep(cooldown)

    # Final summary
    total_final = count_blackbox()
    keys_file = Path("output/keys.txt")
    keys_count = len(keys_file.read_text().strip().splitlines()) if keys_file.exists() else 0

    print()
    print("=" * 60)
    print(f"DONE: {success} OK / {fail} FAIL")
    print(f"Keys file: {keys_count}")
    print(f"9Router: {total_final} active blackbox")
    print("=" * 60)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": N,
        "email_mode": email_mode,
        "success": success,
        "failed": fail,
        "keys_file": keys_count,
        "9router_total": total_final,
        "batches": batch_num,
        "accounts": [
            {
                "email": r.email,
                "api_key": r.api_key[:25] + "..." if r.api_key else "",
                "success": r.success,
                "error": r.error[:80] if r.error else "",
                "elapsed": round(r.elapsed, 2),
            }
            for r in results
        ],
    }
    Path("output/batch_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())

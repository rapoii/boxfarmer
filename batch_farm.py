"""Batch farm — register N accounts and inject to 9Router."""
import asyncio
import os
import secrets
import string
import time
from datetime import datetime, timezone
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from anti_detect import AntiDetect
from injector import inject_key, count_blackbox
from providers.blackbox import BlackboxClient, AccountResult
from providers.tempmail import generate_email


def generate_password(length=16):
    return "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(length))


async def main():
    import json
    import sys

    N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    CONCURRENCY = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    print("=" * 60)
    print(f"BOXFARMER — BATCH FARM ({N} accounts)")
    print(f"Concurrency: {CONCURRENCY}")
    print("=" * 60)
    print()

    current = count_blackbox()
    print(f"  Current 9Router blackbox: {current}")
    print()

    cfg = Config(max_workers=CONCURRENCY, headless=True)
    Path("output").mkdir(exist_ok=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    success = 0
    fail = 0
    results = []

    async def _run(idx):
        nonlocal success, fail
        async with sem:
            ad = AntiDetect(debug=False)
            email = generate_email(cfg.tempmail_domain)
            password = generate_password()

            print(f"  [{idx:02d}] Starting: {email}")
            client = BlackboxClient(cfg, anti_detect=ad)
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
                success += 1
                with open("output/keys.txt", "a", encoding="utf-8") as f:
                    f.write(f"{email}:{password}:{result.api_key}\n")
                try:
                    conn_id = inject_key(email, result.api_key)
                    print(f"  [{idx:02d}] [OK] -> 9Router: {conn_id}")
                except Exception as e:
                    print(f"  [{idx:02d}] [OK] (inject fail: {e})")
            else:
                fail += 1
                print(f"  [{idx:02d}] [FAIL] {result.error[:60]}")

            done = success + fail
            if done % 5 == 0 or done == N:
                total_now = count_blackbox()
                print(f"  [PROGRESS] {done}/{N} (OK:{success} FAIL:{fail}) | 9Router: {total_now}")

    # Stagger launches
    tasks = []
    for i in range(N):
        tasks.append(asyncio.create_task(_run(i + 1)))
        if i < N - 1:
            await asyncio.sleep(secrets.SystemRandom().uniform(*cfg.delay_range))

    await asyncio.gather(*tasks, return_exceptions=True)

    # Final
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
        "success": success,
        "failed": fail,
        "keys_file": keys_count,
        "9router_total": total_final,
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

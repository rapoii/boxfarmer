"""Blackbox.ai Farm — TUI Dashboard."""
from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import string
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from config import Config
from anti_detect import AntiDetect
from injector import find_9router_db, inject_key, count_blackbox, list_blackbox
from providers.blackbox import BlackboxClient, AccountResult
from providers.tempmail import generate_email

STATE_FILE = "state.json"
console = Console(width=60)


def generate_password(length=16):
    return "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(length))


def load_state(output_dir):
    p = Path(output_dir) / STATE_FILE
    if not p.exists():
        return {"target": 0, "accounts": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except:
        return {"target": 0, "accounts": []}


def save_state(output_dir, state):
    p = Path(output_dir) / STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def append_key(output_dir, record):
    p = Path(output_dir) / "keys.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{record['email']}:{record['password']}:{record['api_key']}\n")


def done_emails(state):
    return {a.get("email", "") for a in state.get("accounts", []) if a.get("success")}


def count_keys():
    p = Path("output/keys.txt")
    if not p.exists():
        return 0
    return len([l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()])


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def progress_bar(percent, width=30, color="green"):
    filled = int(width * min(percent, 1.0))
    empty = width - filled
    return f"[{color}]{'=' * filled}[/{color}][dim]{'-' * empty}[/dim]"


def draw_dashboard():
    clear()
    state = load_state("output")
    accounts = state.get("accounts", [])
    ok = len([a for a in accounts if a.get("success")])
    fail = len([a for a in accounts if not a.get("success")])
    total = state.get("target", 0)
    keys = count_keys()
    db = find_9router_db()
    bb_count = count_blackbox() if db else 0

    console.print(Panel(
        Text("BOXFARMER", style="bold white", justify="center"),
        subtitle="Blackbox.ai Account Farm v1.0 | nodriver anti-detect",
        box=box.DOUBLE,
        border_style="cyan",
    ))

    stats = Table(box=None, show_header=False, padding=(0, 2))
    stats.add_column("k", style="dim")
    stats.add_column("v", style="bold")
    stats.add_row("Keys", str(keys))
    stats.add_row("[green]Success[/green]", f"[green]{ok}[/green]")
    stats.add_row("[red]Failed[/red]", f"[red]{fail}[/red]")
    stats.add_row("9Router", f"{bb_count} blackbox")
    console.print(stats)
    console.print()

    if total > 0:
        pct = min(ok / total, 1.0)
        console.print(f"  Progress: {progress_bar(pct)} {ok}/{total} ({int(pct*100)}%)")
    console.print()

    recent = accounts[-20:] if accounts else []
    if recent:
        chart = " ".join(["[green]#[/green]" if a.get("success") else "[red]X[/red]" for a in recent])
        console.print(f"  Last {len(recent)}: {chart}")


def menu_main():
    while True:
        draw_dashboard()
        console.print()
        console.print(Panel.fit(
            "[bold cyan]1[/bold cyan]  Register accounts (batch)\n"
            "[bold cyan]2[/bold cyan]  View registered keys\n"
            "[bold cyan]3[/bold cyan]  Test model via 9Router\n"
            "[bold cyan]4[/bold cyan]  Settings\n"
            "[bold cyan]5[/bold cyan]  Quit",
            title="MENU",
            border_style="green",
        ))

        choice = console.input("\n  > ").strip()

        if choice == "1":
            menu_register()
        elif choice == "2":
            menu_keys()
        elif choice == "3":
            menu_test()
        elif choice == "4":
            menu_settings()
        elif choice == "5":
            console.print("  Bye!")
            break


def menu_register():
    try:
        n = int(console.input("  How many accounts? > ").strip())
    except:
        return

    workers = 3
    try:
        w = console.input(f"  Workers (default {workers})? > ").strip()
        if w:
            workers = int(w)
    except:
        pass

    cfg = Config(max_workers=workers, headless=True)
    state = load_state(cfg.output_dir)
    draw_dashboard()
    console.print(f"\n  [bold]Farming {n} accounts with {workers} workers...[/bold]\n")

    try:
        asyncio.run(_run_batch(cfg, n, state))
    except KeyboardInterrupt:
        console.print("\n  [yellow]Interrupted[/yellow]")

    console.input("\n  Press Enter to continue...")


async def _run_batch(cfg: Config, count: int, state: dict):
    """Run batch registration."""
    sem = asyncio.Semaphore(cfg.max_workers)
    skip = done_emails(state)
    launched = 0
    success = 0
    fail = 0
    tasks = []

    async def _account(idx):
        nonlocal success, fail
        async with sem:
            ad = AntiDetect(debug=True)
            email = generate_email(cfg.tempmail_domain)
            password = generate_password()

            client = BlackboxClient(cfg, anti_detect=ad)
            try:
                await client.start()
                result = await client.register_account(email, password)
            except Exception as e:
                result = AccountResult(email=email, password=password, error=str(e)[:200])
            finally:
                await client.stop()

            record = {
                "email": email,
                "password": password,
                "api_key": result.api_key,
                "success": result.success,
                "error": result.error,
                "elapsed": round(result.elapsed, 2),
            }
            state["accounts"].append(record)
            save_state(cfg.output_dir, state)

            if result.success:
                success += 1
                append_key(cfg.output_dir, record)
                try:
                    conn_id = inject_key(email, result.api_key)
                    console.print(f"  [{idx:02d}] [green]OK[/green] {email} -> {conn_id}")
                except Exception as e:
                    console.print(f"  [{idx:02d}] [green]OK[/green] {email} (inject fail: {e})")
            else:
                fail += 1
                console.print(f"  [{idx:02d}] [red]FAIL[/red] {email} — {result.error[:60]}")

            total_done = success + fail
            console.print(f"  [dim]Progress: {total_done}/{count} (OK:{success} FAIL:{fail})[/dim]")

    for i in range(count):
        tasks.append(asyncio.create_task(_account(i + 1)))
        if i < count - 1:
            delay = secrets.SystemRandom().uniform(*cfg.delay_range)
            await asyncio.sleep(delay)

    await asyncio.gather(*tasks, return_exceptions=True)

    db_count = count_blackbox()
    console.print(f"\n  [bold]Done: {success} OK / {fail} FAIL[/bold]")
    console.print(f"  9Router: {db_count} active blackbox connections")


def menu_keys():
    db = find_9router_db()
    if not db:
        console.print("  [red]9Router DB not found[/red]")
        console.input("  Press Enter...")
        return

    keys = list_blackbox()
    console.print(f"\n  [bold]Blackbox connections in 9Router: {len(keys)}[/bold]\n")

    table = Table(box=box.SIMPLE)
    table.add_column("#", style="dim")
    table.add_column("Name")
    table.add_column("Email")
    table.add_column("Active")
    for i, k in enumerate(keys[:30], 1):
        table.add_row(str(i), k["name"], k.get("email", ""), "✓" if k["isActive"] else "✗")
    console.print(table)
    console.input("\n  Press Enter...")


def menu_test():
    model = console.input("  Model (e.g. bb/gpt-5.4-nano) > ").strip()
    if not model:
        return

    import httpx
    console.print(f"  Testing {model} via 9Router...")
    try:
        resp = httpx.post(
            "http://localhost:20128/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say hello in 3 words"}],
                "max_tokens": 50,
                "stream": False,
            },
            timeout=30,
        )
        data = resp.json()
        if "error" in data:
            console.print(f"  [red]Error: {data['error']['message'][:100]}[/red]")
        else:
            content = data["choices"][0]["message"]["content"]
            console.print(f"  [green]OK[/green]: {content[:100]}")
    except Exception as e:
        console.print(f"  [red]Error: {e}[/red]")

    console.input("\n  Press Enter...")


def menu_settings():
    console.print("\n  [bold]Current Settings:[/bold]")
    console.print(f"  Headless:     True")
    console.print(f"  Workers:      3")
    console.print(f"  Email domain: catchmail.io")
    console.print(f"  Delay range:  3.0 - 10.0s")
    console.print(f"  OTP timeout:  90s")
    console.input("\n  Press Enter...")


if __name__ == "__main__":
    Path("output").mkdir(exist_ok=True)
    menu_main()

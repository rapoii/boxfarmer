# Boxfarmer

Blackbox.ai account farmer with **nodriver** anti-detection.

Bulk register free accounts → harvest API keys → inject to [9Router](https://github.com/your-9router) for model routing.

Each free Blackbox.ai account gives access to **36+ LLM models** (GPT-5.4, DeepSeek V4 Pro, Kimi K3, Grok 4.3, Gemini 3.5 Flash, etc).

## Features

- **nodriver** — undetected-chromedriver based, no Playwright detection
- **Anti-detect** — per-session fingerprint randomization (GPU, viewport, timezone, locale, canvas, WebGL)
- **catchmail.io** — disposable email OTP delivery
- **9Router injection** — auto-inject API keys to 9Router SQLite DB
- **Rich TUI** — interactive dashboard
- **Batch farm** — parallel registration with configurable concurrency

## Quick Start

```bash
pip install -r requirements.txt

# Interactive TUI
python main.py

# Single account test
python test_e2e.py

# Batch farm (20 accounts, 3 workers)
python batch_farm.py 20 3
```

## Usage

### TUI (Interactive)

```bash
python main.py
```

Menu options:
1. Register accounts (batch)
2. View registered keys
3. Test model via 9Router
4. Settings
5. Quit

### Batch Farm

```bash
python batch_farm.py [count] [workers]
```

Default: 20 accounts, 3 concurrent workers.

### Test Single Account

```bash
python test_e2e.py
```

## Configuration

Edit `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_workers` | 3 | Concurrent browser instances |
| `headless` | True | Run browser without UI |
| `tempmail_domain` | catchmail.io | Email domain for OTP |
| `verify_poll_timeout` | 90 | Max seconds to wait for OTP |
| `random_delay_min/max` | 3.0 / 10.0 | Random delay between accounts |

## Anti-Detection

nodriver handles most detection natively. Boxfarmer adds per-session randomization:

| Property | Randomization |
|----------|---------------|
| User-Agent | Chrome 120-128, occasional Edge |
| Viewport | 1280-1920 x 800-1200 |
| WebGL | NVIDIA / AMD / Intel GPU pool |
| Canvas | Per-session noise |
| Platform | Win32 / MacIntel / Linux |
| Cores | 2-20 |
| RAM | 4-32 GB |
| Timezone | 25+ zones worldwide |
| Locale | 22+ locales |

## Requirements

- Python 3.10+
- Google Chrome (nodriver uses system Chrome)

## License

MIT

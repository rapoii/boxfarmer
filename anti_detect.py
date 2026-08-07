"""Lightweight anti-detection for nodriver.

nodriver already handles most fingerprint evasion natively (webdriver flag,
CDP detection, etc). This module adds per-session randomization of
navigator properties to make each account look like a different machine.
"""
from __future__ import annotations

import random
import secrets
import string


# GPU pool for WebGL vendor/renderer
GPU_PROFILES = [
    ("NVIDIA", "NVIDIA GeForce RTX 4090"),
    ("NVIDIA", "NVIDIA GeForce RTX 4080"),
    ("NVIDIA", "NVIDIA GeForce RTX 4070"),
    ("NVIDIA", "NVIDIA GeForce RTX 3080"),
    ("NVIDIA", "NVIDIA GeForce RTX 3070"),
    ("NVIDIA", "NVIDIA GeForce GTX 1660 Ti"),
    ("NVIDIA", "NVIDIA GeForce RTX 2080"),
    ("AMD", "AMD Radeon RX 7900 XTX"),
    ("AMD", "AMD Radeon RX 7800 XT"),
    ("AMD", "AMD Radeon RX 6800 XT"),
    ("AMD", "AMD Radeon RX 6700 XT"),
    ("AMD", "AMD Radeon RX 5700 XT"),
    ("Intel", "Intel(R) Arc(TM) A770 Graphics"),
    ("Intel", "Intel(R) Arc(TM) A750 Graphics"),
    ("Intel", "Intel(R) UHD Graphics 770"),
    ("Intel", "Intel(R) UHD Graphics 730"),
    ("Intel", "Intel(R) Iris(R) Xe Graphics"),
]

TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Los_Angeles",
    "America/Denver", "America/Toronto", "America/Vancouver",
    "Europe/London", "Europe/Berlin", "Europe/Paris", "Europe/Amsterdam",
    "Europe/Moscow", "Europe/Warsaw", "Europe/Rome",
    "Asia/Tokyo", "Asia/Seoul", "Asia/Singapore", "Asia/Dubai",
    "Asia/Shanghai", "Asia/Kolkata", "Asia/Jakarta", "Asia/Bangkok",
    "Australia/Sydney", "Australia/Melbourne",
    "Africa/Nairobi", "Africa/Lagos",
]

LOCALES = [
    "en-US", "en-GB", "en-AU", "en-CA", "en-NZ",
    "de-DE", "fr-FR", "es-ES", "it-IT", "pt-BR", "pt-PT",
    "nl-NL", "pl-PL", "ru-RU", "ja-JP", "ko-KR",
    "zh-CN", "zh-TW", "th-TH", "vi-VN", "id-ID", "tr-TR",
]

PLATFORMS = ["Win32", "Win32", "Win32", "MacIntel", "Linux x86_64"]


class AntiDetect:
    """Per-session fingerprint randomizer for nodriver.

    nodriver already handles the heavy lifting (webdriver flag, CDP
    detection, etc). This just randomizes navigator properties so each
    session looks like a different physical machine.
    """

    def __init__(self, debug: bool = False):
        vendor, renderer = random.choice(GPU_PROFILES)
        self.vendor = vendor
        self.renderer = renderer
        self.platform = random.choice(PLATFORMS)
        self.cores = random.choice([2, 4, 6, 8, 10, 12, 16, 20])
        self.memory = random.choice([4, 8, 16, 32])
        self.timezone = random.choice(TIMEZONES)
        self.locale = random.choice(LOCALES)
        self.screen_w = random.randint(1280, 1920)
        self.screen_h = random.randint(800, 1200)
        self.dpr = random.choice([1.0, 1.25, 1.5, 2.0])
        self.session_id = secrets.token_hex(4)

        if debug:
            self._print()

    def _print(self):
        print(f"  [antidetect] Session: {self.session_id}")
        print(f"  [antidetect] GPU: {self.vendor} {self.renderer}")
        print(f"  [antidetect] Platform: {self.platform}, Cores: {self.cores}, RAM: {self.memory}GB")
        print(f"  [antidetect] TZ: {self.timezone}, Locale: {self.locale}")
        print(f"  [antidetect] Screen: {self.screen_w}x{self.screen_h}, DPR: {self.dpr}")

    def get_init_script(self) -> str:
        """Return JS to inject before page load via addInitScript."""
        return f"""
        // --- boxfarmer anti-detect (session {self.session_id}) ---
        try {{
            Object.defineProperty(navigator, 'platform', {{get: () => '{self.platform}'}});
            Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {self.cores}}});
            Object.defineProperty(navigator, 'deviceMemory', {{get: () => {self.memory}}});
            Object.defineProperty(navigator, 'languages', {{get: () => ['{self.locale}', 'en-US', 'en']}});
            Object.defineProperty(navigator, 'language', {{get: () => '{self.locale}'}});

            // WebGL vendor/renderer
            const _origGetParam = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {{
                if (p === 37445) return '{self.vendor}';
                if (p === 37446) return '{self.renderer}';
                return _origGetParam.call(this, p);
            }};
            if (typeof WebGL2RenderingContext !== 'undefined') {{
                const _origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
                WebGL2RenderingContext.prototype.getParameter = function(p) {{
                    if (p === 37445) return '{self.vendor}';
                    if (p === 37446) return '{self.renderer}';
                    return _origGetParam2.call(this, p);
                }};
            }}

            // Canvas noise (tiny, undetectable)
            const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
                const ctx = this.getContext('2d');
                if (ctx) {{
                    const img = ctx.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < img.data.length; i += 4) {{
                        img.data[i] = img.data[i] ^ (Math.random() < 0.01 ? 1 : 0);
                    }}
                    ctx.putImageData(img, 0, 0);
                }}
                return _origToDataURL.call(this, type, quality);
            }};
        }} catch(e) {{}}
        """

    def get_timezone_script(self) -> str:
        """Return JS to override timezone."""
        return f"""
        try {{
            const _origResolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
            Intl.DateTimeFormat.prototype.resolvedOptions = function() {{
                const opts = _origResolvedOptions.call(this);
                opts.timeZone = '{self.timezone}';
                return opts;
            }};
        }} catch(e) {{}}
        """

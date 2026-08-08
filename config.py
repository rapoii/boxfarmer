"""Application configuration for boxfarmer."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Config:
    """Static run configuration."""
    blackbox_url: str = "https://app.blackbox.ai"
    email_mode: str = "catchmail"  # "catchmail" or "generator"
    tempmail_domain: str = "catchmail.io"
    max_workers: int = 3
    verify_poll_timeout: int = 90
    verify_poll_interval: int = 3
    request_timeout: int = 30
    output_dir: str = "output"
    headless: bool = True
    random_delay_min: float = 3.0
    random_delay_max: float = 10.0
    key_name: str = "auto-farm-key"
    generator_preferred_domain: str = ""  # empty = random domain from generator.email

    @property
    def delay_range(self) -> tuple[float, float]:
        return (self.random_delay_min, self.random_delay_max)

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_path: Path
    admin_api_key: str
    cors_origins: list[str]
    rate_limit_verify_per_minute: int
    require_https_sdk: bool
    bind_public: bool

    @classmethod
    def from_env(cls) -> Settings:
        db_default = Path(__file__).resolve().parents[1] / "data" / "checkout_bank.db"
        cors_raw = os.getenv("CHECKOUT_CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080")
        return cls(
            host=os.getenv("CHECKOUT_BANK_HOST", "127.0.0.1"),
            port=int(os.getenv("CHECKOUT_BANK_PORT", "8090")),
            database_path=Path(os.getenv("CHECKOUT_BANK_DB", str(db_default))),
            admin_api_key=os.getenv(
                "CHECKOUT_BANK_ADMIN_KEY",
                "change-me-before-production",
            ),
            cors_origins=[o.strip() for o in cors_raw.split(",") if o.strip()],
            rate_limit_verify_per_minute=int(os.getenv("CHECKOUT_RATE_LIMIT_VERIFY", "120")),
            require_https_sdk=os.getenv("CHECKOUT_REQUIRE_HTTPS", "false").lower() == "true",
            bind_public=os.getenv("CHECKOUT_BIND_PUBLIC", "false").lower() == "true",
        )

    @property
    def listen_host(self) -> str:
        return "0.0.0.0" if self.bind_public else self.host

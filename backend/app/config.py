"""All settings come from environment variables (see ../.env.example). No secrets live in code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE, '#' comments, optional quotes). Real environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if val[:1] in ("'", '"') and val.count(val[0]) >= 2:
            val = val[1:val.index(val[0], 1)]
        else:
            if val.startswith("#"):
                val = ""                                        # "KEY=   # comment" means empty
            else:
                val = val.split(" #", 1)[0].strip()
        os.environ.setdefault(key.strip(), val)


load_dotenv(Path(__file__).resolve().parents[1] / ".env")      # backend/.env


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL", "postgresql://flood:flood@localhost:5433/flood_db"))
    # --- model ---
    model_provider: str = field(default_factory=lambda: os.getenv("MODEL_PROVIDER", "gnn").strip().lower())
    ml_dir: Path = field(default_factory=lambda: Path(os.getenv("ML_DIR", str(REPO_ROOT / "ml"))))
    model_path: Path = field(default_factory=lambda: Path(os.getenv(
        "MODEL_PATH", str(REPO_ROOT / "ml" / "checkpoints_v3" / "best_model_v3.pt"))))
    # --- simulation clock: every tick advances the model by ONE 5-minute step ---
    inference_interval_seconds: float = field(default_factory=lambda: float(os.getenv("INFERENCE_INTERVAL_SECONDS", "5")))
    stale_after_seconds: float = field(default_factory=lambda: float(os.getenv("STALE_AFTER_SECONDS", "30")))
    # --- routing ---
    spatial_join_radius_m: float = 75.0
    flood_cost_multiplier: float = 10_000.0
    bbox_margin_deg: float = 0.003
    max_snap_distance_m: float = 250.0
    route_speed_kmh: float = field(default_factory=lambda: float(os.getenv("ROUTE_SPEED_KMH", "20")))
    # --- auth ---
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    jwt_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("JWT_TTL_MINUTES", "480")))
    bootstrap_user: str = field(default_factory=lambda: os.getenv("BOOTSTRAP_ADMIN_ID", ""))
    bootstrap_password: str = field(default_factory=lambda: os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""))
    # --- http ---
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173"))
    # --- misc ---
    prediction_sample_seconds: float = field(default_factory=lambda: float(os.getenv("PREDICTION_SAMPLE_SECONDS", "300")))
    blockage_effective: bool = field(default_factory=lambda: _bool("BLOCKAGE_EFFECTIVE", False))

    def validate(self) -> None:
        if len(self.jwt_secret) < 32:
            raise RuntimeError(
                "JWT_SECRET must be set to a random string of at least 32 characters. "
                "Generate one with:  python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
        if self.model_provider not in ("gnn", "mock"):
            raise RuntimeError(f"MODEL_PROVIDER must be 'gnn' or 'mock', got {self.model_provider!r}")


def load_settings() -> Settings:
    s = Settings()
    s.validate()
    return s

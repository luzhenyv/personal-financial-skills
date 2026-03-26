"""Application configuration loaded from environment variables."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    """Application settings from .env file or environment."""

    # Database
    database_url: str = "sqlite:///./data/personal_finance.db"
    sqlite_database_path: Path = Path("./data/personal_finance.db")

    # SEC EDGAR
    sec_user_agent: str = ""  # required — set in .env
    sec_base_url: str = "https://data.sec.gov"
    sec_rate_limit: float = 0.12  # seconds between requests (max 10/sec)

    # Alpha Vantage
    alpha_vantage_key: str = ""  # set in .env
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"

    # FRED
    fred_api_key: str = ""  # set in .env

    # Paths
    data_dir: Path = Path("./data")

    # App
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:8501"

    model_config = {"extra": "ignore"}

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    def ticker_artifacts_dir(self, ticker: str) -> Path:
        """Return the artifacts directory for *ticker* (``data/artifacts/{ticker}``)."""
        return self.artifacts_dir / ticker

    def ticker_profile_dir(self, ticker: str) -> Path:
        """Return the profile artifacts directory (``data/artifacts/{ticker}/profile/``)."""
        return self.artifacts_dir / ticker / "profile"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    def ensure_dirs(self) -> None:
        """Create data directories if they don't exist."""
        for d in [self.raw_dir, self.artifacts_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgresql(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

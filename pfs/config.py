"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from .env file or environment."""

    # Database
    database_url: str = "postgresql://pfs:pfs_dev_2024@localhost:5432/personal_finance"

    # SEC EDGAR
    sec_user_agent: str = "PersonalFinanceApp your_email@example.com"
    sec_base_url: str = "https://data.sec.gov"
    sec_rate_limit: float = 0.12  # seconds between requests (max 10/sec)

    # Alpha Vantage
    alpha_vantage_key: str = ""
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"

    # FRED
    fred_api_key: str = ""

    # Paths
    data_dir: Path = Path("./data")

    # App
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

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


settings = Settings()

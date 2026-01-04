# src/market_spine/domains/otc/connector.py

"""HTTP download capability - Intermediate tier adds this."""

import httpx
from pathlib import Path

from market_spine.domains.otc.parser import parse_finra_content
from market_spine.domains.otc.models import RawRecord


class OTCConnector:
    """
    Fetch FINRA files via HTTP.

    Basic tier only reads local files.
    Intermediate adds HTTP download.
    """

    FINRA_BASE = "https://www.finra.org/finra-data"
    TIMEOUT = 30

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or Path("data/finra")
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def download(self, url: str) -> list[RawRecord]:
        """Download and parse FINRA file from URL."""
        with httpx.Client(timeout=self.TIMEOUT) as client:
            response = client.get(url)
            response.raise_for_status()
            content = response.text

        return list(parse_finra_content(content))

    def download_and_cache(self, url: str, filename: str) -> Path:
        """Download file and save locally."""
        with httpx.Client(timeout=self.TIMEOUT) as client:
            response = client.get(url)
            response.raise_for_status()

        path = self.data_dir / filename
        path.write_text(response.text)
        return path

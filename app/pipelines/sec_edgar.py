"""
SEC EDGAR pipeline for downloading SEC filings.

Case Study 2: Downloads 10-K, 10-Q, 8-K filings for target companies
using the sec-edgar-downloader library.
"""

import logging
from pathlib import Path

from sec_edgar_downloader import Downloader

logger = logging.getLogger(__name__)


class SECEdgarPipeline:
    """Pipeline for downloading SEC filings."""

    def __init__(
        self,
        company_name: str,
        email: str,
        download_dir: Path = Path("data/raw/sec"),
    ):
        """
        Initialize the SEC EDGAR pipeline.

        Args:
            company_name: Name to identify your application
            email: Your email address for SEC API compliance
            download_dir: Directory to store downloaded filings
        """
        self.dl = Downloader(company_name, email, download_dir)
        self.download_dir = download_dir

    def download_filings(
        self,
        ticker: str,
        filing_types: list[str] = ["10-K", "10-Q", "8-K"],
        limit: int = 10,
        after: str = "2020-01-01",
    ) -> list[Path]:
        """
        Download filings for a company.

        Args:
            ticker: Company ticker symbol
            filing_types: List of filing types to download
            limit: Maximum filings per type
            after: Only filings after this date (YYYY-MM-DD)

        Returns:
            List of paths to downloaded filings
        """
        downloaded = []

        for filing_type in filing_types:
            try:
                self.dl.get(filing_type, ticker, limit=limit, after=after)

                # Find downloaded files
                filing_dir = (
                    self.download_dir
                    / "sec-edgar-filings"
                    / ticker
                    / filing_type
                )
                if filing_dir.exists():
                    for filing_path in filing_dir.glob("**/full-submission.txt"):
                        downloaded.append(filing_path)
                        logger.info(f"Downloaded: {filing_path}")

            except Exception as e:
                logger.error(
                    f"Error downloading {filing_type} for {ticker}: {e}"
                )

        return downloaded

from __future__ import annotations

from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.models import FetchResult
from config.constants import USER_AGENT, HTML_TYPES

def create_session() -> requests.Session:
    """Creates a requests session with a custom user agent and retry strategy."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": ", ".join(HTML_TYPES),
    })
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class Fetcher:
    """A class to fetch web pages with retry logic and error handling."""
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self.session = create_session()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self.session.close()

    def fetch(self, url: str) -> FetchResult:
        """
        Fetches the content of a web page.
        
        Args:
            url (str): The URL of the web page to fetch.
        
        Returns:
            FetchResult: The result of the fetch operation.
        """
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            return FetchResult(url, fetched_at, None, None, error=f"{type(exc).__name__}: {exc}")

        def fail(error: str) -> FetchResult:
            """
            Helper function to create a FetchResult for failed requests.
            
            Args:
                error (str): The error message.
            
            Returns:
                FetchResult: The fetch result indicating failure.
            """
            return FetchResult(url, fetched_at, response.url, response.status_code, error=error)

        if response.status_code != 200:
            return fail(f"HTTP {response.status_code}: {response.reason}")

        content_type = response.headers.get("Content-Type", "")
        mime_type = content_type.split(";", 1)[0].strip().lower()
        if mime_type not in HTML_TYPES:
            return fail(f"Expected HTML; received {mime_type}")

        if "charset=" not in content_type.lower():
            response.encoding = response.apparent_encoding or "utf-8"

        return FetchResult(url, fetched_at, response.url, response.status_code, html=response.text)
from datetime import datetime, timezone
import math

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import FetchResult

USER_AGENT = "TestScrapeUser"
HTML_TYPES = {"text/html", "application/xhtml+xml"}


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html, application/xhtml+xml",
    })
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    for scheme in ("http://", "https://"):
        session.mount(scheme, HTTPAdapter(max_retries=retry))
    return session


class Fetcher:

    def __init__(
        self, session: requests.Session | None = None, timeout: float = 10.0
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        self._timeout = timeout
        self._owns_session = session is None
        self._session = session if session is not None else create_session()
        self._closed = False

    def __enter__(self) -> "Fetcher":
        if self._closed:
            raise RuntimeError("Fetcher is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            if self._owns_session:
                self._session.close()
            self._closed = True

    def fetch(self, url: str) -> FetchResult:
        if self._closed:
            raise RuntimeError("Fetcher is closed")
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        final_url = None
        status_code = None
        try:
            with self._session.get(url, timeout=self._timeout, allow_redirects=True) as response:
                final_url = response.url
                status_code = response.status_code
                if status_code != 200:
                    return FetchResult(url, fetched_at, final_url, status_code,
                                       error=f"HTTP {status_code}: {response.reason}")
                content_type = response.headers.get("Content-Type", "")
                mime_type = content_type.split(";", 1)[0].strip().lower()
                if mime_type not in HTML_TYPES:
                    return FetchResult(url, fetched_at, final_url, status_code,
                                       error=f"Expected HTML; received {mime_type or 'no Content-Type'}")


                if "charset=" not in content_type.lower().replace(" ", ""):
                    from bs4 import UnicodeDammit

                    decoded = UnicodeDammit(response.content, is_html=True)
                    html = decoded.unicode_markup
                    if html is None:
                        response.encoding = response.apparent_encoding or "utf-8"
                        html = response.text
                else:
                    html = response.text
                return FetchResult(url, fetched_at, final_url, status_code, html=html)
        except requests.RequestException as exc:
            return FetchResult(url, fetched_at, final_url, status_code,
                               error=f"{type(exc).__name__}: {exc}")


def fetch(
    url: str, session: requests.Session | None = None, timeout: float = 10.0
) -> FetchResult:
    with Fetcher(session=session, timeout=timeout) as fetcher:
        return fetcher.fetch(url)

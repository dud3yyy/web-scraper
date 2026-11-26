from contextlib import nullcontext
import logging
import math
import time
from urllib.parse import (
    parse_qsl,
    urlencode,
    urldefrag,
    urljoin,
    urlsplit,
    urlunsplit,
)

from .fetcher import Fetcher
from config.models import PageRecord
from .parser import find_next_url, parse

logger = logging.getLogger(__name__)

def validate_url(url: str) -> str:
    """
    Validate and normalize a URL.

    Raises ValueError if the URL is invalid.
    Args:
        url: The URL to validate.
    Returns:
        str: The normalized URL.
    """
    url = urldefrag(url.strip())[0]

    try:
        parts = urlsplit(url)

        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError("Expected an absolute HTTP(S) URL")

        if parts.username or parts.password:
            raise ValueError("URLs with embedded credentials are not supported")

        parts.port  # Validate port
        if any(char.isspace() for char in url):
            raise ValueError("URL contains whitespace")

    except ValueError as exc:
        raise ValueError(f"Invalid URL {url!r}: {exc}") from exc

    return url


def url_key(url: str) -> str:
    """
    Return a normalized key for a URL.

    Args:  
        url: The URL to normalize.
    Returns:
        str: The normalized URL key.
    """
    parts = urlsplit(validate_url(url))

    host = parts.hostname.lower()
    if ":" in host:  # IPv6
        host = f"[{host}]"

    port = parts.port
    if port and (parts.scheme.lower(), port) not in {
        ("http", 80),
        ("https", 443),
    }:
        host += f":{port}"

    return urlunsplit((
        parts.scheme.lower(),
        host,
        parts.path or "/",
        parts.query,
        "",
    ))


def bump_page_param(url: str, page_param: str) -> str:
    """
    Increment the value of a pagination parameter in a URL.
    
    Raises:
      ValueError if the parameter is missing, repeated, or not a nonnegative integer.
    Args:
        url: The URL to modify.
        page_param: The name of the pagination parameter to increment.  
    Returns:
        str: The modified URL with the pagination parameter incremented.
    """
    if not page_param or not page_param.strip():
        raise ValueError("Page parameter cannot be empty")

    parts = urlsplit(validate_url(url))
    params = parse_qsl(parts.query, keep_blank_values=True)

    values = [value for key, value in params if key == page_param]

    if len(values) > 1:
        raise ValueError(f"Repeated pagination parameter: {page_param}")

    value = values[0] if values else "1"

    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"Pagination parameter {page_param!r} must be a nonnegative integer")

    next_value = str(int(value) + 1)

    params = [
        (key, next_value if key == page_param else value)
        for key, value in params
    ]

    if not values:
        params.append((page_param, next_value))

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(params),
        "",
    ))


class Crawler:
    """
    A web crawler for fetching and parsing web pages.
    """
    def __init__(
        self,
        max_pages: int = 10,
        delay: float = 1.0,
        next_selector: str | None = None,
        page_param: str | None = None,
        fetcher: Fetcher | None = None,
    ):
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")

        if not math.isfinite(delay) or delay < 0:
            raise ValueError("delay must be a nonnegative finite number")

        if next_selector is not None and not next_selector.strip():
            raise ValueError("next_selector cannot be empty")

        if page_param is not None and not page_param.strip():
            raise ValueError("page_param cannot be empty")

        self.max_pages = max_pages
        self.delay = delay
        self.next_selector = next_selector
        self.page_param = page_param
        self.fetcher = fetcher

    def crawl(self, start_url: str) -> list[PageRecord]:
        """
        Crawl web pages starting from the given URL.
        Args:
            start_url: The starting URL for the crawl.
        Returns:
            list[PageRecord]: A list of PageRecord objects containing the parsed content and metadata of
        """
        start_url = validate_url(start_url)
        current_url = start_url

        visited = set()
        records = []

        context = nullcontext(self.fetcher) if self.fetcher else Fetcher()

        with context as fetcher:
            while len(records) < self.max_pages:
                key = url_key(current_url)

                if key in visited:
                    break

                if records:
                    time.sleep(self.delay)

                visited.add(key)

                result = fetcher.fetch(current_url)

                if result.error is not None:
                    logger.error("Failed to fetch %s: %s", current_url, result.error)
                    break

                final_url = validate_url(result.final_url or current_url)
                final_key = url_key(final_url)

                if final_key != key and final_key in visited:
                    logger.info("Stopping: redirect returned to an already visited page")
                    break

                visited.add(final_key)

                if result.html is None or result.status_code is None:
                    raise ValueError("Successful FetchResult must contain html and status_code")

                content = parse(result.html, final_url)

                record = {
                    **content,
                    "start_url": start_url,
                    "page_index": len(records) + 1,
                    "url": current_url,
                    "final_url": final_url,
                    "status_code": result.status_code,
                    "fetched_at": result.fetched_at,
                    "next_url": None,
                }

                records.append(record)

                if len(records) >= self.max_pages:
                    break

                next_url = find_next_url(
                    result.html,
                    final_url,
                    selector=self.next_selector,
                )

                if not next_url and self.page_param:
                    next_url = bump_page_param(final_url, self.page_param)

                if not next_url or next_url.strip().startswith("#"):
                    break

                try:
                    next_url = validate_url(urljoin(final_url, next_url))
                except ValueError:
                    logger.warning("Stopping: invalid pagination URL %r", next_url)
                    break

                if url_key(next_url) in visited:
                    break

                record["next_url"] = next_url
                current_url = next_url

        return records

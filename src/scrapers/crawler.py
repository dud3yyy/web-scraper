from contextlib import nullcontext
import logging
import math
import time
from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlsplit, urlunsplit

from .fetcher import Fetcher
from .models import PageRecord
from .parser import find_next_url, parse

logger = logging.getLogger(__name__)


def validate_url(url: str) -> str:
    url = urldefrag(url.strip())[0]
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError("expected an absolute HTTP(S) URL")
        if parts.username is not None or parts.password is not None:
            raise ValueError("URLs with embedded credentials are not supported")
        _ = parts.port
        if any(char.isspace() for char in url):
            raise ValueError("URL contains whitespace")
    except ValueError as exc:
        raise ValueError(f"Invalid URL {url!r}: {exc}") from exc
    return url


def _url_key(url: str) -> str:
    parts = urlsplit(validate_url(url))
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    if port is not None and (parts.scheme.lower(), port) not in {("http", 80), ("https", 443)}:
        host += f":{port}"
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, ""))


def bump_page_param(url: str, page_param: str) -> str:
    if not page_param or not page_param.strip():
        raise ValueError("page parameter cannot be empty")
    parts = urlsplit(validate_url(url))
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    values = [value for key, value in pairs if key == page_param]
    if len(values) > 1:
        raise ValueError(f"Repeated pagination parameter: {page_param}")
    value = values[0] if values else "1"
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"Pagination parameter {page_param!r} must be a nonnegative integer")
    next_value = str(int(value) + 1)
    updated = [(key, next_value if key == page_param else item) for key, item in pairs]
    if not values:
        updated.append((page_param, next_value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(updated), ""))


class Crawler:

    def __init__(
        self,
        max_pages: int = 10,
        delay: float = 1.0,
        next_selector: str | None = None,
        page_param: str | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("delay must be a nonnegative finite number")
        if next_selector is not None and not next_selector.strip():
            raise ValueError("next_selector cannot be empty")
        if page_param is not None and not page_param.strip():
            raise ValueError("page_param cannot be empty")
        self._max_pages = max_pages
        self._delay = delay
        self._next_selector = next_selector
        self._page_param = page_param
        self._fetcher = fetcher

    def crawl(self, start_url: str) -> list[PageRecord]:
        max_pages = self._max_pages
        delay = self._delay
        next_selector = self._next_selector
        page_param = self._page_param
        start_url = validate_url(start_url)
        current_url = start_url
        visited: set[str] = set()
        records: list[PageRecord] = []
        with (nullcontext(self._fetcher) if self._fetcher is not None else Fetcher()) as fetcher:
            for _ in range(max_pages):
                key = _url_key(current_url)
                if key in visited:
                    break
                if records:
                    time.sleep(delay)

                    records[-1]["next_url"] = current_url
                visited.add(key)
                result = fetcher.fetch(current_url)
                if result.error is not None:
                    logger.error("Failed to fetch %s: %s", current_url, result.error)
                    break
                final_url = validate_url(result.final_url or current_url)
                final_key = _url_key(final_url)
                if final_key != key and final_key in visited:
                    logger.info("Stopping: redirect returned to an already visited page")
                    break
                visited.add(final_key)
                if result.html is None or result.status_code is None:
                    raise ValueError("Successful FetchResult must contain html and status_code")
                content = parse(result.html, final_url)
                record: PageRecord = {
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
                if len(records) >= max_pages:
                    break
                next_url = find_next_url(result.html, final_url, selector=next_selector)
                if not next_url and page_param is not None:
                    next_url = bump_page_param(final_url, page_param)
                if not next_url or not next_url.strip() or next_url.strip().startswith("#"):
                    break
                try:
                    candidate = validate_url(urljoin(final_url, next_url))
                except ValueError:
                    logger.warning("Stopping: invalid pagination URL %r", next_url)
                    break
                if _url_key(candidate) in visited:
                    break
                current_url = candidate
        return records


def crawl(
    start_url: str,
    max_pages: int = 10,
    delay: float = 1.0,
    next_selector: str | None = None,
    page_param: str | None = None,
) -> list[PageRecord]:
    return Crawler(
        max_pages=max_pages, delay=delay,
        next_selector=next_selector, page_param=page_param,
    ).crawl(start_url)

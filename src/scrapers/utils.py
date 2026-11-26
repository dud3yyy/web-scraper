
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag


def clean_text(tag: Tag | None) -> str:
    if not tag:
        return ""
    return " ".join(tag.get_text(" ", strip=True).split())


def unique(items: list) -> list:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def get_base_url(soup: BeautifulSoup, url: str) -> str:
    base = soup.find("base", href=True)
    return urljoin(url, base["href"]) if base else url


def get_http_url(base_url: str, href: str) -> str | None:
    try:
        url = urljoin(base_url, href.strip())
        parts = urlsplit(url)

        if parts.scheme in {"http", "https"} and parts.hostname:
            return url
    except ValueError:
        pass

    return None

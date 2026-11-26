
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag


def clean_text(tag: Tag | None) -> str:
    """Clean the text of a BeautifulSoup tag by removing extra whitespace and joining the text content.
    
    Args:
        tag (Tag | None): A BeautifulSoup Tag object or None.
        
    Returns:
        str: The cleaned text content.
    """
    if not tag:
        return ""
    return " ".join(tag.get_text(" ", strip=True).split())


def unique(items: list) -> list:
    """Return a list of unique items, preserving order.
    
    Args:
        items (list): A list of items.
        
    Returns:
        list: A list of unique items.
    """
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def get_base_url(soup: BeautifulSoup, url: str) -> str:
    """Get the base URL from a BeautifulSoup object or fallback to the provided URL.
    
    Args:
        soup (BeautifulSoup): A BeautifulSoup object.
        url (str): The original URL.
        
    Returns:
        str: The base URL.
    """
    base = soup.find("base", href=True)
    return urljoin(url, base["href"]) if base else url


def get_http_url(base_url: str, href: str) -> str | None:
    """Get a valid HTTP URL from a base URL and a relative href.
    
    Args:
        base_url (str): The base URL.
        href (str): The relative URL.
        
    Returns:
        str | None: The valid HTTP URL or None if invalid.
    """
    try:
        url = urljoin(base_url, href.strip())
        parts = urlsplit(url)

        if parts.scheme in {"http", "https"} and parts.hostname:
            return url
    except ValueError:
        pass

    return None

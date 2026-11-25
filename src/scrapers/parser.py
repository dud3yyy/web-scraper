from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .models import ParsedContent


def parse(html: str, url: str) -> ParsedContent:
    soup = BeautifulSoup(html, "html.parser")
    base = soup.find("base", href=True)
    base_url = urljoin(url, base["href"]) if base else url

    def text(tag) -> str:
        return " ".join(tag.get_text(" ", strip=True).split())

    meta = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property")
        if name and tag.get("content") is not None:
            meta[str(name)] = str(tag["content"]).strip()
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        item = {"level": int(tag.name[1]), "text": text(tag)}
        if item["text"] and item not in headings:
            headings.append(item)
    paragraphs = list(dict.fromkeys(text(tag) for tag in soup.find_all("p") if text(tag)))
    links = []
    for tag in soup.find_all("a", href=True):
        href = _http_url(base_url, str(tag["href"]))
        item = {"text": text(tag), "href": href}
        if href and item not in links:
            links.append(item)
    images = []
    for tag in soup.find_all("img", src=True):
        src = _http_url(base_url, str(tag["src"]))
        item = {"src": src, "alt": tag.get("alt")}
        if src and item not in images:
            images.append(item)
    return {
        "title": text(soup.title) or None if soup.title else None,
        "meta": meta, "headings": headings, "paragraphs": paragraphs,
        "links": links, "images": images,
    }


def _http_url(base_url: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith("#"):
        return None
    try:
        resolved = urljoin(base_url, href)
        parts = urlsplit(resolved)
        if parts.scheme in {"http", "https"} and parts.hostname:
            return resolved
    except ValueError:
        pass
    return None


def find_next_url(html: str, base_url: str, selector: str | None = None) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    base = soup.find("base", href=True)
    if base:
        base_url = urljoin(base_url, base["href"])
    if selector is not None:
        candidates = soup.select(selector)
    else:
        candidates = list(soup.select('head link[rel~="next"], a[rel~="next"]'))
        labels = {"next", "next page", "older", "older posts", "›", "»", "→"}
        for tag in soup.find_all("a", href=True):
            label = " ".join(str(tag.get("aria-label") or tag.get_text(" ", strip=True)).lower().split())
            cleaned = label.strip(" ›»→")
            if label in labels or cleaned in labels:
                candidates.append(tag)

        candidates.sort(key=lambda tag: 0 if tag.name == "link" else 1)
    for tag in candidates:
        if str(tag.get("aria-disabled", "")).lower() == "true":
            continue
        result = _http_url(base_url, str(tag.get("href", "")))
        if result:
            return result
    return None

import json
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from config.models import ParsedContent
from config.constants import MIN_REPEATS, MIN_FIELDS, NEXT_LABELS

def _text(tag: Tag | None) -> str:
    return " ".join(tag.get_text(" ", strip=True).split()) if tag else ""


def _unique(items) -> list:
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _base_url(soup: BeautifulSoup, url: str) -> str:
    base = soup.find("base", href=True)
    return urljoin(url, base["href"]) if base else url


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


def parse(html: str, url: str) -> ParsedContent:
    soup = BeautifulSoup(html, "html.parser")
    base_url = _base_url(soup, url)

    meta = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property")
        if name and tag.get("content") is not None:
            meta[str(name)] = str(tag["content"]).strip()

    json_ld = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            json_ld.append(json.loads(tag.string or ""))
        except ValueError:
            pass

    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    collections = _collections(soup, base_url)
    items = [item for collection in collections for item in collection["items"]]
    seen_links = {link["href"] for item in items for link in item.get("links", [])}
    seen_images = {src for item in items for src in item.get("images", [])}

    return {
        "title": _text(soup.title) or None,
        "meta": meta,
        "json_ld": json_ld,
        "headings": _unique(
            {"level": int(tag.name[1]), "text": text}
            for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
            if (text := _text(tag))
        ),
        "paragraphs": _unique(text for tag in soup.find_all("p") if (text := _text(tag))),
        "links": _unique(
            {"text": _text(tag), "href": href}
            for tag in soup.find_all("a", href=True)
            if (href := _http_url(base_url, str(tag["href"]))) and href not in seen_links
        ),
        "images": _unique(
            {"src": src, "alt": tag.get("alt")}
            for tag in soup.find_all("img", src=True)
            if (src := _http_url(base_url, str(tag["src"]))) and src not in seen_images
        ),
        "tables": _tables(soup),
        "collections": collections,
    }

def _tables(soup: BeautifulSoup) -> list[dict]:
    tables = []
    for table in soup.find_all("table"):
        rows = [[_text(cell) for cell in tr.find_all(["th", "td"])] for tr in table.find_all("tr")]
        rows = [row for row in rows if any(row)]
        if len(rows) > 1:
            tables.append({"header": rows[0], "rows": rows[1:]})
    return tables


def _is_field(tag: Tag) -> bool:
    return bool(tag.get("class") or tag.get("itemprop"))


def _fields(block: Tag) -> dict[str, list[str]]:
    """Maps each leaf element with a class/itemprop to its text, keyed by that name."""
    fields: dict[str, list[str]] = {}
    for tag in block.find_all(True):
        if tag.name == "meta" or not _is_field(tag):
            continue
        if any(_is_field(inner) for inner in tag.find_all(True)):
            continue  # a wrapper; its children are the real fields
        key = str(tag.get("itemprop") or tag["class"][0])
        if value := _text(tag):
            fields.setdefault(key, []).append(value)
    return fields


def _collections(soup: BeautifulSoup, base_url: str) -> list[dict]:
    groups = {}
    for tag in soup.find_all(class_=True):
        groups.setdefault((id(tag.parent), tag.name, tuple(tag["class"])), []).append(tag)

    collections, claimed = [], set()
    for blocks in groups.values():
        if len(blocks) < MIN_REPEATS:
            continue
        if any(id(parent) in claimed for block in blocks for parent in block.parents):
            continue  # already covered by an enclosing group

        parsed = [(block, _fields(block)) for block in blocks]
        parsed = [(block, fields) for block, fields in parsed if len(fields) >= MIN_FIELDS]
        if len(parsed) < MIN_REPEATS:
            continue

        # A key is a list in every record if any record has several values for it,
        # so the shape stays consistent (e.g. quotes with one tag vs. many tags).
        multi = {key for _, fields in parsed for key, values in fields.items() if len(values) > 1}

        items = []
        for block, fields in parsed:
            item = {k: (v if k in multi else v[0]) for k, v in fields.items()}
            captured = {value for values in fields.values() for value in values}
            links = _unique(
                {"text": text, "href": href}
                for a in block.find_all("a", href=True)
                if (text := _text(a)) not in captured
                and (href := _http_url(base_url, str(a["href"])))
            )
            images = _unique(
                src for img in block.find_all("img", src=True)
                if (src := _http_url(base_url, str(img["src"])))
            )
            if links:
                item["links"] = links
            if images:
                item["images"] = images
            items.append(item)

        claimed.update(id(block) for block, _ in parsed)
        collections.append({
            "selector": f"{blocks[0].name}.{'.'.join(blocks[0]['class'])}",
            "count": len(items),
            "items": items,
        })
    return collections


def find_next_url(html: str, base_url: str, selector: str | None = None) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    base_url = _base_url(soup, base_url)

    if selector is not None:
        candidates = soup.select(selector)
    else:
        candidates = list(soup.select('head link[rel~="next"], a[rel~="next"]'))
        for tag in soup.find_all("a", href=True):
            label = " ".join(str(tag.get("aria-label") or tag.get_text(" ", strip=True)).lower().split())
            if label in NEXT_LABELS or label.strip(" ›»→") in NEXT_LABELS:
                candidates.append(tag)
        candidates.sort(key=lambda tag: tag.name != "link")  # <link rel="next"> first

    for tag in candidates:
        if str(tag.get("aria-disabled", "")).lower() == "true":
            continue
        if result := _http_url(base_url, str(tag.get("href", ""))):
            return result
    return None
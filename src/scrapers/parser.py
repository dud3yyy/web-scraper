import json

from bs4 import BeautifulSoup, Tag

from config.models import ParsedContent
from config.constants import (
    MIN_REPEATS,
    MIN_FIELDS,
    NEXT_LABELS,
    IGNORED_TAGS,
    HEADING_TAGS,
    TABLE_CELL_TAGS,
    NEXT_LINK_SELECTOR,
)
from scrapers.utils import (
    clean_text,
    unique,
    get_base_url,
    get_http_url,
)


def parse(html: str, url: str) -> ParsedContent:
    """Parse the HTML content of a web page and extract structured information.
    Args
        html (str): The HTML content of the web page.
        url (str): The URL of the web page.
    Returns:
        ParsedContent: A dataclass containing the parsed information, including title, meta tags, JSON-LD data, headings, paragraphs, links, images, tables, and collections."""
    soup = BeautifulSoup(html, "html.parser")
    base_url = get_base_url(soup, url)

    meta = {
        tag.get("name") or tag.get("property"): tag["content"].strip()
        for tag in soup.find_all("meta")
        if (tag.get("name") or tag.get("property"))
        and tag.get("content") is not None
    }

    json_ld = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            json_ld.append(json.loads(tag.string or ""))
        except (ValueError, TypeError):
            continue

    for tag in soup(IGNORED_TAGS):
        tag.decompose()

    collections = extract_collections(soup, base_url)

    items = [
        item
        for collection in collections
        for item in collection["items"]
    ]

    seen_links = {
        link["href"]
        for item in items
        for link in item.get("links", [])
    }

    seen_images = {
        image
        for item in items
        for image in item.get("images", [])
    }

    return {
        "title": clean_text(soup.title) or None,
        "meta": meta,
        "json_ld": json_ld,
        "headings": unique([
            {"level": int(tag.name[1]), "text": text}
            for tag in soup.find_all(HEADING_TAGS)
            if (text := clean_text(tag))
        ]),
        "paragraphs": unique([
            clean_text(tag)
            for tag in soup.find_all("p")
            if clean_text(tag)
        ]),
        "links": unique([
            {"text": clean_text(tag), "href": href}
            for tag in soup.find_all("a", href=True)
            if (href := get_http_url(base_url, str(tag["href"])))
            and href not in seen_links
        ]),
        "images": unique([
            {"src": src, "alt": tag.get("alt")}
            for tag in soup.find_all("img", src=True)
            if (src := get_http_url(base_url, str(tag["src"])))
            and src not in seen_images
        ]),
        "tables": extract_tables(soup),
        "collections": collections,
    }


def extract_tables(soup: BeautifulSoup) -> list[dict]:
    """Extract tables from the BeautifulSoup object and return them as a list of dictionaries.
    Args:
        soup (BeautifulSoup): A BeautifulSoup object representing the parsed HTML.
    Returns:
        list[dict]: A list of dictionaries, each containing the header and rows of a table.
    """
    tables = []

    for table in soup.find_all("table"):
        rows = [
            [clean_text(cell) for cell in row.find_all(TABLE_CELL_TAGS)]
            for row in table.find_all("tr")
        ]

        rows = [row for row in rows if any(row)]

        if len(rows) > 1:
            tables.append({
                "header": rows[0],
                "rows": rows[1:],
            })

    return tables


def extract_fields(block: Tag) -> dict[str, list[str]]:
    """
    Extract named fields from a BeautifulSoup Tag block and return them as a dictionary.
    Args:
        block (Tag): A BeautifulSoup Tag object representing the block to extract fields from.
    Returns:
        dict[str, list[str]]: A dictionary containing the extracted fields.
    """
    fields = {}

    for tag in block.find_all(True):
        key = tag.get("itemprop") or (tag.get("class") or [None])[0]

        if not key or tag.name == "meta":
            continue

        if any(
            inner.get("itemprop") or inner.get("class")
            for inner in tag.find_all(True)
        ):
            continue

        if value := clean_text(tag):
            fields.setdefault(str(key), []).append(value)

    return fields


def extract_collections(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract collections of similar blocks from the BeautifulSoup object and return them as a list of dictionaries.
    Args:
        soup (BeautifulSoup): A BeautifulSoup object representing the parsed HTML.
        base_url (str): The base URL of the web page.
    Returns:
        list[dict]: A list of dictionaries, each containing the selector, count, and items of a collection.
    """
    groups = {}

    for tag in soup.find_all(class_=True):
        key = (id(tag.parent), tag.name, tuple(tag["class"]))
        groups.setdefault(key, []).append(tag)

    collections = []
    claimed = set()

    for blocks in groups.values():
        if len(blocks) < MIN_REPEATS:
            continue

        if any(
            id(parent) in claimed
            for block in blocks
            for parent in block.parents
        ):
            continue

        parsed = [(block, extract_fields(block)) for block in blocks]
        parsed = [
            (block, fields)
            for block, fields in parsed
            if len(fields) >= MIN_FIELDS
        ]

        if len(parsed) < MIN_REPEATS:
            continue

        multi = {
            key
            for _, fields in parsed
            for key, values in fields.items()
            if len(values) > 1
        }

        items = []

        for block, fields in parsed:
            item = {
                key: values if key in multi else values[0]
                for key, values in fields.items()
            }

            captured = {
                value
                for values in fields.values()
                for value in values
            }

            links = unique([
                {"text": clean_text(tag), "href": href}
                for tag in block.find_all("a", href=True)
                if (text := clean_text(tag)) not in captured
                and (href := get_http_url(base_url, str(tag["href"])))
            ])

            images = unique([
                src
                for tag in block.find_all("img", src=True)
                if (src := get_http_url(base_url, str(tag["src"])))
            ])

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


def find_next_url(
    html: str,
    base_url: str,
    selector: str | None = None,
) -> str | None:
    """Find the URL of the next page in a paginated web page.
    Args:
        html (str): The HTML content of the web page.
        base_url (str): The base URL of the web page.
        selector (str | None): An optional CSS selector to find the next link. If not provided, a default selector will be used.
    Returns:
        str | None: The URL of the next page, or None if not found.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_url = get_base_url(soup, base_url)

    if selector:
        candidates = soup.select(selector)
    else:
        candidates = soup.select(NEXT_LINK_SELECTOR)

        for tag in soup.find_all("a", href=True):
            label = " ".join(
                str(tag.get("aria-label") or tag.get_text(" ", strip=True))
                .lower()
                .split()
            )

            if label in NEXT_LABELS or label.strip(" ›»→") in NEXT_LABELS:
                candidates.append(tag)

        candidates.sort(key=lambda tag: tag.name != "link")

    for tag in candidates:
        if tag.get("aria-disabled") == "true":
            continue

        if url := get_http_url(base_url, str(tag.get("href", ""))):
            return url

    return None

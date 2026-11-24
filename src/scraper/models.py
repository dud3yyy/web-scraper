from dataclasses import dataclass
from typing import TypedDict


class Heading(TypedDict):
    level: int
    text: str


class Link(TypedDict):
    text: str
    href: str


class Image(TypedDict):
    src: str
    alt: str | None


class ParsedContent(TypedDict):
    title: str | None
    meta: dict[str, str]
    headings: list[Heading]
    paragraphs: list[str]
    links: list[Link]
    images: list[Image]


class PageRecord(ParsedContent):
    start_url: str
    page_index: int
    url: str
    final_url: str
    status_code: int
    fetched_at: str
    next_url: str | None


@dataclass(frozen=True)
class FetchResult:
    url: str
    fetched_at: str
    final_url: str | None = None
    status_code: int | None = None
    html: str | None = None
    error: str | None = None

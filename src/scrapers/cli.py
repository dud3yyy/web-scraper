import argparse
import logging
import math
import time
from pathlib import Path

from .crawler import Crawler, validate_url
from .models import PageRecord
from writers.json_writer import JSONWriter 


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _delay(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative number") from exc
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative finite number")
    return number


class _FailureCounter(logging.Handler):

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract static HTML pages and follow pagination.")
    parser.add_argument("urls", nargs="*", help="one or more absolute HTTP(S) URLs")
    parser.add_argument("--urls-file", type=Path, help="UTF-8 file with one URL per line; # comments allowed")
    parser.add_argument("--output", type=Path, default=Path("output/results"), help="output file or base name (default: output/results)")
    parser.add_argument("--format", choices=("json",), default="json")
    parser.add_argument("--delay", type=_delay, default=1.0, help="seconds between pages (default: 1)")
    parser.add_argument("--max-pages", type=_positive_int, default=10, help="maximum pages per starting URL (default: 10)")
    parser.add_argument("--page-param", help="integer query parameter to increment when no next link is found")
    parser.add_argument("--next-selector", help="CSS selector overriding automatic next-link detection")
    return parser


def _output_path(path: Path) -> Path:
    return path if path.suffix else path.with_suffix(".json")


class ScraperCLI:

    def __init__(self) -> None:
        self._parser = build_parser()

    def run(self, argv: list[str] | None = None) -> int:
        parser = self._parser
        args = parser.parse_args(argv)
        urls = list(args.urls)
        if args.urls_file:
            try:
                urls.extend(line.strip() for line in args.urls_file.read_text(encoding="utf-8-sig").splitlines()
                            if line.strip() and not line.lstrip().startswith("#"))
            except (OSError, UnicodeError) as exc:
                parser.error(f"cannot read URL file: {exc}")
        if not urls:
            parser.error("provide at least one URL or --urls-file")
        try:
            urls = list(dict.fromkeys(validate_url(url) for url in urls))
        except ValueError as exc:
            parser.error(str(exc))
        for name in ("page_param", "next_selector"):
            value = getattr(args, name)
            if value is not None and not value.strip():
                parser.error(f"--{name.replace('_', '-')} cannot be empty")
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        logger = logging.getLogger("scraper")
        counter = _FailureCounter()
        logger.addHandler(counter)
        records: list[PageRecord] = []
        try:
            crawler = Crawler(
                max_pages=args.max_pages, delay=args.delay,
                next_selector=args.next_selector, page_param=args.page_param,
            )
            for index, url in enumerate(urls):
                if index:
                    time.sleep(args.delay)
                records.extend(crawler.crawl(url))
            if not records:
                logger.error("No pages were collected; no output was written.")
                return 1
            path = _output_path(args.output)
            writer = JSONWriter(path)
            writer.write(records)
            logger.info("Wrote %s pages to %s", len(records), path)
            return 1 if counter.count else 0
        except (OSError, ValueError, UnicodeError) as exc:
            logger.error("Scraper stopped: %s", exc)
            return 1
        except KeyboardInterrupt:
            logger.warning("Interrupted.")
            return 130
        finally:
            logger.removeHandler(counter)


def main(argv: list[str] | None = None) -> int:
    return ScraperCLI().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())


import argparse
import logging
import math
import time
from pathlib import Path

from scrapers.crawler import Crawler, validate_url
from config.models import PageRecord
from writers.json_writer import JSONWriter


def positive_int(value: str) -> int:
    """Validate that the provided value is a positive integer.
    Args:
        value (str): The value to validate.
    Returns:
        int: The validated positive integer.
    Raises:
        argparse.ArgumentTypeError: If the value is not a positive integer."""
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be a positive integer"
        ) from exc

    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")

    return number


def delay_value(value: str) -> float:
    """Validate that the provided value is a nonnegative finite number.
    Args:
        value (str): The value to validate.
    Returns:
        float: The validated nonnegative finite number.
    Raises:
        argparse.ArgumentTypeError: If the value is not a nonnegative finite number."""
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be a nonnegative number"
        ) from exc

    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError(
            "must be a nonnegative finite number"
        )

    return number


class FailureCounter(logging.Handler):
    """A logging handler that counts the number of error messages emitted."""
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.count = 0

    def emit(self, record: logging.LogRecord):
        self.count += 1


def build_parser() -> argparse.ArgumentParser:
    """Build and return the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Extract static HTML pages and follow pagination."
    )

    parser.add_argument(
        "urls",
        nargs="*",
        help="one or more absolute HTTP(S) URLs",
    )
    parser.add_argument(
        "--urls-file",
        type=Path,
        help="UTF-8 file with one URL per line; # comments allowed",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/results"),
        help="output file or base name (default: output/results)",
    )
    parser.add_argument("--format", choices=("json",), default="json")
    parser.add_argument(
        "--delay",
        type=delay_value,
        default=1.0,
        help="seconds between pages (default: 1)",
    )
    parser.add_argument(
        "--max-pages",
        type=positive_int,
        default=10,
        help="maximum pages per starting URL (default: 10)",
    )
    parser.add_argument(
        "--page-param",
        help="integer query parameter to increment when no next link is found",
    )
    parser.add_argument(
        "--next-selector",
        help="CSS selector overriding automatic next-link detection",
    )

    return parser


def load_urls(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    """Load and validate URLs from command-line arguments and an optional file.
    
    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        parser (argparse.ArgumentParser): The argument parser for error reporting.
    Returns:
        list[str]: A list of validated unique URLs.
    Raises:
            SystemExit: If no valid URLs are provided.
    """
    urls = list(args.urls)

    if args.urls_file:
        try:
            lines = args.urls_file.read_text(encoding="utf-8-sig").splitlines()
            urls.extend(
                line.strip()
                for line in lines
                if line.strip() and not line.lstrip().startswith("#")
            )
        except (OSError, UnicodeError) as exc:
            parser.error(f"cannot read URL file: {exc}")

    if not urls:
        parser.error("provide at least one URL or --urls-file")

    try:
        urls = list(dict.fromkeys(validate_url(url) for url in urls))
    except ValueError as exc:
        parser.error(str(exc))

    if args.page_param is not None and not args.page_param.strip():
        parser.error("--page-param cannot be empty")

    if args.next_selector is not None and not args.next_selector.strip():
        parser.error("--next-selector cannot be empty")

    return urls


def output_path(path: Path) -> Path:
    """Ensure the output path has a .json suffix.
    
    Args:
        path (Path): The intended output path.
    
    Returns:
        Path: The revised output path with the appropriate suffix.
    """
    return path if path.suffix else path.with_suffix(".json")


def run(argv: list[str] | None = None) -> int:
    """Run the web scraper with the provided command-line arguments."""
    parser = build_parser()
    args = parser.parse_args(argv)
    urls = load_urls(args, parser)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    logger = logging.getLogger("scrapers")
    counter = FailureCounter()
    logger.addHandler(counter)

    records: list[PageRecord] = []

    try:
        crawler = Crawler(
            max_pages=args.max_pages,
            delay=args.delay,
            next_selector=args.next_selector,
            page_param=args.page_param,
        )

        for index, url in enumerate(urls):
            if index:
                time.sleep(args.delay)

            records.extend(crawler.crawl(url))

        if not records:
            logger.error("No pages were collected; no output was written.")
            return 1

        path = output_path(args.output)
        JSONWriter(path).write(records)

        logger.info("Wrote %s pages to %s", len(records), path)

        return 1 if counter.count else 0

    except KeyboardInterrupt:
        logger.warning("Interrupted.")
        return 130

    except (OSError, ValueError) as exc:
        logger.error("Scraper stopped: %s", exc)
        return 1

    finally:
        logger.removeHandler(counter)


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the web scraper command-line interface."""
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

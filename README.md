# Web Scraper

A command-line scraper for static HTML pages, built with Python, requests, and
BeautifulSoup. It follows pagination and saves one JSON record per page.

It extracts HTML categories such as headings and links, not semantic categories
such as books or products. Menus and footer content may be included in the output.

## Setup and usage

Requires Python 3.12 or newer and uv. Run from the project directory:

```powershell
python -m pip install uv
python -m uv sync --python 3.12
python -m uv run scraper --help
python -m uv run scraper https://quotes.toscrape.com/ --max-pages 3 --format json
python -m uv run scraper https://www.awesomebooks.com/ --max-pages 1 --output output/awesomebooks.json
```

Open `output/results.json` to inspect the default output. Rerunning overwrites the
file. JSON is the only output format.

| Argument | Default | Purpose |
| --- | --- | --- |
| Positional URLs | None | One or more starting URLs |
| `--urls-file` | None | UTF-8 file with one URL per line |
| `--output` | `output/results` | Output file or base name |
| `--format` | `json` | Optional; accepts only `json` |
| `--max-pages` | `10` | Page limit per starting URL |
| `--delay` | `1.0` | Seconds between pages and starting URLs |
| `--page-param` | None | Numeric query parameter to increment |
| `--next-selector` | None | CSS selector for the next-page link |

URL files ignore blank lines and lines beginning with `#`. File and positional
URLs can be combined; duplicate starting URLs are removed in their original order.
A supplied filename suffix is kept; `.json` is added if there is no suffix.

## Project structure

```text
src/
  main.py                 Source-directory launcher
  scraper/
    __init__.py           Package marker
    __main__.py           Module launcher
    cli.py                Arguments and application coordination
    crawler.py            Pagination and page collection
    fetcher.py            HTTP requests and session management
    models.py             Shared data structures
    parser.py             HTML extraction and next-link detection
    writers.py            JSON file output
```

`pyproject.toml` defines dependencies, packaging, and the `scraper` command.
`uv.lock` records dependency versions; `.python-version` selects Python 3.12.
`.venv` contains installed libraries and the project's interpreter. `.gitignore`
excludes generated files and output. `.vscode` contains local editor settings.

## Execution flow

1. `main()` creates a `ScraperCLI` and calls `run()`.
2. The CLI validates arguments, loads URLs, and creates a `Crawler`.
3. The crawler uses a `Fetcher` to download a page.
4. `parse()` extracts content from the HTML.
5. The crawler adds metadata and follows the next-page URL until a stop condition.
6. The CLI sends the collected records to `write_json()`.

A fetch failure stops that pagination chain and is logged. Other starting URLs
can still be processed. Successfully collected records are exported; if there
are no records, no output is written.

## Classes

### Fetcher - fetcher.py

Owns the request timeout and a reusable HTTP session.

- `__init__(session=None, timeout=10.0)` validates the timeout and stores an existing
  session or creates one. `_owns_session` tracks responsibility for cleanup.
- `fetch(url)` sends a GET request, follows redirects, requires HTTP 200 and an
  HTML Content-Type, decodes the response, and returns a `FetchResult`. Network
  exceptions are returned in its `error` field.
- `close()` closes an internally created session and marks the fetcher as closed.
  Repeated calls are safe. Caller-supplied sessions remain open.
- `__enter__()` and `__exit__()` support `with Fetcher() as fetcher:` and ensure
  cleanup when leaving the block, including on exceptions.

The internal attributes are `_timeout`, `_session`, `_owns_session`, and `_closed`.
A leading underscore marks implementation details by convention, not enforced privacy.

`create_session()` configures headers and up to three retries for eligible errors,
with backoff and Retry-After support. The timeout is not a total crawl deadline.
When no charset is declared, BeautifulSoup's UnicodeDammit helps decode the HTML.
The module-level `fetch()` function creates a Fetcher, calls it, and cleans up.

### Crawler - crawler.py

Stores pagination settings and coordinates downloading and parsing.

- `__init__(max_pages=10, delay=1.0, next_selector=None, page_param=None,
  fetcher=None)` validates and stores configuration. A Fetcher can be supplied.
- `crawl(start_url)` returns a list of page records. Each call starts with a new
  visited set and results list. By default it creates and closes its own Fetcher;
  an injected Fetcher remains the caller's responsibility.

The crawler stops on the page limit, a repeated requested/final URL, a fetch
failure, an invalid next URL, or no next URL. Cross-site next links are allowed.

Supporting functions:

- `validate_url()` requires HTTP(S), a hostname and valid port, rejects whitespace
  and embedded credentials, and removes fragments.
- `_url_key()` normalizes scheme/host case and default ports for loop detection.
  Arbitrary query-parameter ordering is not normalized.
- `bump_page_param()` increments a nonnegative integer query value by one while
  preserving other values. An absent parameter means page 1, giving page 2 next.
  Repeated parameters and invalid values are rejected; larger offset steps are unsupported.
- `crawl()` is a convenience wrapper around the class.

### ScraperCLI - cli.py

Owns the argument parser and coordinates a command.

- `__init__()` creates its parser through `build_parser()`.
- `run(argv=None)` reads arguments and URL files, validates input, removes duplicate
  starting URLs, creates a Crawler, collects records, chooses filenames, and invokes
  the writers. It handles common operational errors and Ctrl+C and returns an exit code.

`_positive_int()` validates the page limit. `_delay()` validates finite nonnegative
delays. `_output_path()` builds filenames. `main()` creates a ScraperCLI and calls it.

Exit codes: 0 for success, 1 for operational failure (including partial success),
2 for invalid arguments, and 130 for interruption.

### _FailureCounter - cli.py

Inherits from `logging.Handler`. Its constructor sets an error-level threshold
and initializes `count`; `emit()` increments it for each received error message.
This lets the CLI return a failure status even when some pages were saved successfully.

### Shared types - models.py

| Class | Fields and purpose |
| --- | --- |
| `Heading` | Numeric `level` and heading `text` |
| `Link` | Visible `text` and absolute `href` |
| `Image` | Absolute `src` and optional `alt` text |
| `ParsedContent` | `title`, `meta`, `headings`, `paragraphs`, `links`, `images` |
| `PageRecord` | ParsedContent fields plus crawl metadata below |
| `FetchResult` | `url`, `fetched_at`, `final_url`, `status_code`, `html`, `error` |

The first five use TypedDict: they describe ordinary dictionaries for editors and
type checkers without runtime validation. PageRecord inherits ParsedContent's fields.

FetchResult is a frozen dataclass. Python generates its initialization and representation
methods; fields cannot normally be reassigned after creation. Success contains HTML
and status 200 with no error. Failure contains an error message and may lack response data.

## Parser and writers

`parse(html, url)` extracts common content with BeautifulSoup, removes script,
style, noscript, and template elements, normalizes whitespace, and deduplicates items.
Relative URLs use the final response URL or an HTML base element. Only HTTP(S)
links and image URLs are included.

`find_next_url(html, base_url, selector=None)` uses an explicit selector exclusively,
or looks for head `link[rel=next]`, then `a[rel=next]`, then recognized next-link
text/labels. It ignores empty, fragment-only, non-HTTP(S), and explicitly aria-disabled
links. A selector must select an element with an href. If no link is found, the crawler
can fall back to the configured page parameter.

`write_json(records, path)` creates parent directories and writes UTF-8 JSON with
two-space indentation and readable Unicode characters. Existing files are overwritten.

## JSON records

One record represents one successfully parsed page. Alongside ParsedContent fields:

| Field | Meaning |
| --- | --- |
| `start_url` | Starting URL of the chain |
| `page_index` | Position in the chain, starting at 1 |
| `url` | Requested URL |
| `final_url` | URL after redirects |
| `status_code` | Successful page's HTTP status |
| `fetched_at` | UTC ISO 8601 timestamp recorded before the request |
| `next_url` | Next URL actually requested, or null if no further request was made |

The next request can fail, so next_url does not guarantee another record exists.
Failed pages are not exported. Missing titles are null and missing collections are empty.

## Using the classes directly

```python
from scraper.crawler import Crawler
from scraper.fetcher import Fetcher
from scraper.writers import write_json

with Fetcher(timeout=10.0) as fetcher:
    crawler = Crawler(max_pages=3, delay=1.0, fetcher=fetcher)
    records = crawler.crawl("https://quotes.toscrape.com/")
    write_json(records, "output/results.json")
```

Configuration and behavior are kept together (encapsulation). Crawler uses Fetcher
(composition), while _FailureCounter extends logging.Handler and overrides emit
(inheritance and method overriding). Pure helpers remain functions.

The installed command, `python src/main.py`, and `python -m scraper` all reach the
same CLI when run in the project environment.

## Limitations and verification

- No JavaScript execution, infinite scroll, login workflow, GUI, or database.
- Images come from `img src`; lazy-loading attributes, srcset, and CSS backgrounds
  are not collected.
- Paragraphs come from `p` elements. Other text is not automatically included.
- No site-specific book, product, or listing records.
- No robots.txt handling or response-size limit.
- Different URLs serving identical content are not detected as duplicate pages.

Syntax, imports, and CLI startup have been checked. Manual JSON runs collected
three pages from Quotes to Scrape and one homepage each from AwesomeBooks and MerrJep.
These runs do not establish compatibility with every site or edge case. There is
currently no automated test suite.

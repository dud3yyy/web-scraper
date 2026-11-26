
# Constants for the web scraper
USER_AGENT = "TestScrapeUser"
HTML_TYPES = {"text/html", "application/xhtml+xml"}

NEXT_LABELS = {"next", "next page", "older", "older posts", "›", "»", "→"}
MIN_REPEATS = 3  # a group needs at least this many sibling blocks
MIN_FIELDS = 2   # and each block needs at least this many named fields

IGNORED_TAGS = ["script", "style", "noscript", "template"]
HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
TABLE_CELL_TAGS = ["th", "td"]

NEXT_LINK_SELECTOR = 'head link[rel~="next"], a[rel~="next"]'
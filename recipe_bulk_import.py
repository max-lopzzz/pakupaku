"""
recipe_bulk_import.py
----------------------
Bulk recipe import: given a blog index/archive URL, discover the
individual recipe post links on it and run recipe_import.py's existing
per-URL extraction pipeline over each one. Nothing is saved here —
callers get back a list of RecipeImportDraft objects for review, same
as a single import.
"""

import asyncio
import logging
from typing import List, Optional
from urllib.parse import urljoin, urlparse
import re

from bs4 import BeautifulSoup
from fastapi import HTTPException

from recipe_import import build_import_draft, fetch_page
from schemas import RecipeImportDraft

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  LINK DISCOVERY
# ─────────────────────────────────────────────

# Common non-post URL shapes on blog platforms. Deliberately conservative:
# a link that slips through this filter costs nothing, since
# bulk_extract_drafts() below treats "no recipe found" as a normal,
# silently-dropped outcome. A link wrongly excluded here is a real recipe
# that never gets a chance — worse, so the list stays short.
_EXCLUDED_PATH_PATTERNS = [
    re.compile(r"/tag/", re.IGNORECASE),
    re.compile(r"/category/", re.IGNORECASE),
    re.compile(r"/author/", re.IGNORECASE),
    re.compile(r"/page/\d+", re.IGNORECASE),
    re.compile(r"/search", re.IGNORECASE),
]
_EXCLUDED_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".pdf", ".xml", ".css", ".js", ".ico",
)


def _is_excluded_path(path: str) -> bool:
    lowered = path.lower()
    if lowered.endswith(_EXCLUDED_EXTENSIONS):
        return True
    return any(p.search(lowered) for p in _EXCLUDED_PATH_PATTERNS)


def _extract_candidate_links(
    soup: BeautifulSoup, page_url: str, base_host: Optional[str]
) -> List[str]:
    """Same-domain <a> hrefs on one archive page that look like individual
    post pages: not the page itself, not a bare fragment, not a
    tag/category/author/pagination/search URL, not a non-HTML file, and
    not cross-domain. In first-seen order; may repeat within the page —
    discover_recipe_links() dedupes across the whole crawl."""
    normalized_page = page_url.split("#")[0]

    links: List[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#"):
            continue

        absolute = urljoin(page_url, href)
        normalized = absolute.split("#")[0]
        if not normalized or normalized == normalized_page:
            continue

        parsed = urlparse(normalized)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.hostname != base_host:
            continue
        if _is_excluded_path(parsed.path):
            continue

        links.append(normalized)

    return links


def _find_next_page_url(
    soup: BeautifulSoup, page_url: str, base_host: Optional[str]
) -> Optional[str]:
    """The "next page" link on a paginated archive, if any: a
    <link rel="next">, an <a rel="next">, or the standard WordPress
    <a class="next page-numbers">. Resolved to an absolute same-host URL;
    None if there's no next page or it points off-domain."""
    hrefs: List[str] = []
    for finder in (
        lambda: soup.find("link", rel=lambda v: bool(v) and "next" in v),
        lambda: soup.find("a", rel=lambda v: bool(v) and "next" in v),
        lambda: soup.select_one("a.next.page-numbers, a.page-numbers.next"),
    ):
        tag = finder()
        if tag and tag.get("href"):
            hrefs.append(tag["href"].strip())

    for href in hrefs:
        if not href or href.startswith("#"):
            continue
        normalized = urljoin(page_url, href).split("#")[0]
        parsed = urlparse(normalized)
        if parsed.scheme in ("http", "https") and parsed.hostname == base_host:
            return normalized

    return None


async def discover_recipe_links(index_url: str) -> List[str]:
    """Starting from index_url, walk the archive's pagination (following
    each page's "next page" link) and return every same-domain link that
    looks like an individual post page. Deduped, in first-seen order.

    Pages are fetched one at a time, in order. Already-visited archive
    pages are tracked so a pagination cycle can't loop forever. If the
    first page can't be fetched the error propagates; if a later page
    fails, whatever was discovered up to that point is returned.

    This is a permissive heuristic, not a recipe classifier — pages that
    slip through get filtered for real by bulk_extract_drafts(), which
    only keeps URLs where build_import_draft() actually found a recipe.
    """
    base_host = urlparse(index_url).hostname

    seen: set = set()
    candidates: List[str] = []
    visited_pages: set = set()

    next_url: Optional[str] = index_url.split("#")[0]
    while next_url and next_url not in visited_pages:
        visited_pages.add(next_url)
        try:
            html = await fetch_page(next_url)
        except HTTPException:
            if not candidates and len(visited_pages) == 1:
                raise
            logger.warning(
                "discover_recipe_links: stopping early, failed to fetch %r", next_url
            )
            break

        soup = BeautifulSoup(html, "html.parser")
        for link in _extract_candidate_links(soup, next_url, base_host):
            if link in seen or link in visited_pages:
                continue
            seen.add(link)
            candidates.append(link)

        next_url = _find_next_page_url(soup, next_url, base_host)

    return candidates


# ─────────────────────────────────────────────
#  BATCH EXTRACTION
# ─────────────────────────────────────────────

_MAX_CONCURRENT_EXTRACTIONS = 5


async def _safe_build_import_draft(
    url: str, semaphore: asyncio.Semaphore
) -> Optional[RecipeImportDraft]:
    async with semaphore:
        try:
            return await build_import_draft(url)
        except HTTPException:
            return None
        except Exception:
            logger.exception(
                "bulk_extract_drafts: unexpected failure extracting %r", url
            )
            return None


async def bulk_extract_drafts(urls: List[str]) -> List[RecipeImportDraft]:
    """Run build_import_draft() over every URL, concurrency-bounded to
    _MAX_CONCURRENT_EXTRACTIONS in-flight extractions so a large batch
    can't hammer the source site or the LLM endpoint all at once. URLs
    where extraction fails (no recipe found, fetch error, anything
    build_import_draft raises HTTPException for) are silently dropped —
    mirrors recipe_import.py's _safe_match_ingredient, so one bad URL in
    a batch can't sink the whole run."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EXTRACTIONS)
    results = await asyncio.gather(
        *(_safe_build_import_draft(url, semaphore) for url in urls)
    )
    return [draft for draft in results if draft is not None]

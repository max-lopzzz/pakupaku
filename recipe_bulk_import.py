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


async def discover_recipe_links(index_url: str) -> List[str]:
    """Fetch index_url and return same-domain links that look like
    individual post pages: not the index page itself, not a bare
    fragment, not a tag/category/author/pagination/search URL, not a
    non-HTML file, and not cross-domain. Deduped, in first-seen order.

    This is a permissive heuristic, not a recipe classifier — pages that
    slip through get filtered for real by bulk_extract_drafts(), which
    only keeps URLs where build_import_draft() actually found a recipe.
    """
    html = await fetch_page(index_url)
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(index_url).hostname
    normalized_index = index_url.split("#")[0]

    seen = set()
    candidates: List[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#"):
            continue

        absolute = urljoin(index_url, href)
        normalized = absolute.split("#")[0]
        if not normalized or normalized == normalized_index:
            continue

        parsed = urlparse(normalized)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.hostname != base_host:
            continue
        if _is_excluded_path(parsed.path):
            continue
        if normalized in seen:
            continue

        seen.add(normalized)
        candidates.append(normalized)

    return candidates

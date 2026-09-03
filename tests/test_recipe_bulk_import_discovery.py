# tests/test_recipe_bulk_import_discovery.py
from pathlib import Path

import pytest
from fastapi import HTTPException

import recipe_bulk_import
from recipe_bulk_import import discover_recipe_links

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


async def test_discover_recipe_links_filters_and_dedupes(monkeypatch):
    async def fake_fetch_page(url):
        assert url == "https://recipeblog.example.com/category/desserts/"
        return _read("blog_index_page.html")

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    result = await discover_recipe_links("https://recipeblog.example.com/category/desserts/")

    assert result == [
        "https://recipeblog.example.com/recipes/chocolate-cake/",
        "https://recipeblog.example.com/recipes/banana-bread/",
        "https://recipeblog.example.com/recipes/garlic-soup",
    ]


async def test_discover_recipe_links_returns_empty_list_when_none_found(monkeypatch):
    async def fake_fetch_page(url):
        return "<html><body><p>No links here.</p></body></html>"

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    result = await discover_recipe_links("https://example.com/index/")
    assert result == []


def _archive_page(recipe_slugs, next_href=None):
    articles = "".join(
        f'<article><a href="/recipes/{slug}/">{slug}</a></article>'
        for slug in recipe_slugs
    )
    head = f'<link rel="next" href="{next_href}">' if next_href else ""
    nav = f'<a class="next page-numbers" href="{next_href}">Next Page</a>' if next_href else ""
    return f"<html><head>{head}</head><body><main>{articles}{nav}</main></body></html>"


async def test_discover_recipe_links_follows_pagination(monkeypatch):
    pages = {
        "https://blog.example.com/category/recipes/": _archive_page(
            ["a", "b"], next_href="https://blog.example.com/category/recipes/page/2/"
        ),
        "https://blog.example.com/category/recipes/page/2/": _archive_page(
            ["c", "d"], next_href="https://blog.example.com/category/recipes/page/3/"
        ),
        "https://blog.example.com/category/recipes/page/3/": _archive_page(["e"]),
    }
    fetched = []

    async def fake_fetch_page(url):
        fetched.append(url)
        return pages[url]

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    result = await discover_recipe_links("https://blog.example.com/category/recipes/")

    assert result == [
        "https://blog.example.com/recipes/a/",
        "https://blog.example.com/recipes/b/",
        "https://blog.example.com/recipes/c/",
        "https://blog.example.com/recipes/d/",
        "https://blog.example.com/recipes/e/",
    ]
    assert fetched == [
        "https://blog.example.com/category/recipes/",
        "https://blog.example.com/category/recipes/page/2/",
        "https://blog.example.com/category/recipes/page/3/",
    ]


async def test_discover_recipe_links_dedupes_across_pages(monkeypatch):
    pages = {
        "https://blog.example.com/recipes/": _archive_page(
            ["a", "b"], next_href="https://blog.example.com/recipes/page/2/"
        ),
        "https://blog.example.com/recipes/page/2/": _archive_page(["b", "c"]),
    }

    async def fake_fetch_page(url):
        return pages[url]

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    result = await discover_recipe_links("https://blog.example.com/recipes/")

    assert result == [
        "https://blog.example.com/recipes/a/",
        "https://blog.example.com/recipes/b/",
        "https://blog.example.com/recipes/c/",
    ]


async def test_discover_recipe_links_stops_on_pagination_cycle(monkeypatch):
    pages = {
        "https://blog.example.com/recipes/": _archive_page(
            ["a"], next_href="https://blog.example.com/recipes/page/2/"
        ),
        "https://blog.example.com/recipes/page/2/": _archive_page(
            ["b"], next_href="https://blog.example.com/recipes/"
        ),
    }
    fetched = []

    async def fake_fetch_page(url):
        fetched.append(url)
        return pages[url]

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    result = await discover_recipe_links("https://blog.example.com/recipes/")

    assert result == [
        "https://blog.example.com/recipes/a/",
        "https://blog.example.com/recipes/b/",
    ]
    assert fetched == [
        "https://blog.example.com/recipes/",
        "https://blog.example.com/recipes/page/2/",
    ]


async def test_discover_recipe_links_returns_partial_on_later_page_failure(monkeypatch):
    pages = {
        "https://blog.example.com/recipes/": _archive_page(
            ["a"], next_href="https://blog.example.com/recipes/page/2/"
        ),
    }

    async def fake_fetch_page(url):
        if url not in pages:
            raise HTTPException(status_code=422, detail="Could not fetch that URL.")
        return pages[url]

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    result = await discover_recipe_links("https://blog.example.com/recipes/")

    assert result == ["https://blog.example.com/recipes/a/"]


async def test_discover_recipe_links_raises_when_first_page_fails(monkeypatch):
    async def fake_fetch_page(url):
        raise HTTPException(status_code=422, detail="Could not fetch that URL.")

    monkeypatch.setattr(recipe_bulk_import, "fetch_page", fake_fetch_page)

    with pytest.raises(HTTPException):
        await discover_recipe_links("https://blog.example.com/recipes/")

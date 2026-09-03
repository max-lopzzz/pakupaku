# tests/test_recipe_bulk_import_discovery.py
from pathlib import Path

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

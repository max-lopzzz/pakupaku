import asyncio

from fastapi import HTTPException

import recipe_bulk_import
from recipe_bulk_import import bulk_extract_drafts
from schemas import RecipeImportDraft


async def test_bulk_extract_drafts_drops_failures_and_keeps_successes(monkeypatch):
    calls = []

    async def fake_build_import_draft(url):
        calls.append(url)
        if url == "https://example.com/good-1":
            return RecipeImportDraft(
                name="Good One", servings=2.0, image_url=None,
                ingredients=[], source_url=url,
            )
        if url == "https://example.com/good-2":
            return RecipeImportDraft(
                name="Good Two", servings=1.0, image_url=None,
                ingredients=[], source_url=url,
            )
        raise HTTPException(status_code=422, detail="Couldn't find a recipe on that page.")

    monkeypatch.setattr(recipe_bulk_import, "build_import_draft", fake_build_import_draft)

    result = await bulk_extract_drafts([
        "https://example.com/good-1",
        "https://example.com/bad",
        "https://example.com/good-2",
    ])

    assert sorted(calls) == sorted([
        "https://example.com/good-1", "https://example.com/bad", "https://example.com/good-2",
    ])
    assert sorted(d.name for d in result) == ["Good One", "Good Two"]


async def test_bulk_extract_drafts_bounds_concurrency(monkeypatch):
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def fake_build_import_draft(url):
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        async with lock:
            in_flight -= 1
        return RecipeImportDraft(
            name=url, servings=1.0, image_url=None, ingredients=[], source_url=url,
        )

    monkeypatch.setattr(recipe_bulk_import, "build_import_draft", fake_build_import_draft)

    urls = [f"https://example.com/post-{i}" for i in range(20)]
    result = await bulk_extract_drafts(urls)

    assert len(result) == 20
    assert max_in_flight <= 5

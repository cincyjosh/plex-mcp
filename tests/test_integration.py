# tests/test_integration.py
"""Integration tests that run against a live Plex server.

Requires a .env file in the project root with:
    PLEX_SERVER_URL=https://your-plex-server:32400
    PLEX_TOKEN=yourPlexTokenHere

Run with:
    uv run pytest -m integration
"""

import pytest
from dotenv import load_dotenv

load_dotenv()

from plex_mcp import (
    get_plex_server,
    search_movies,
    get_movie_details,
    get_movie_genres,
    recent_movies,
    most_watched,
    get_similar_movies,
    get_watch_history,
    get_on_deck,
    get_library_stats,
    search_tv_shows,
    get_show_details,
    list_playlists,
    search_music,
    get_artist_details,
    get_album_details,
    get_similar_artists,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_movie_key(result: str) -> str:
    """Extract the first ratingKey from a search_movies result string."""
    for line in result.splitlines():
        if line.strip().startswith("Key:"):
            return line.split("Key:")[1].strip()
    return ""


def _first_key_from_result(result: str) -> str:
    """Extract the first [key: ...] value from any result string."""
    import re
    m = re.search(r'\[key:\s*(\d+)\]', result)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_connect():
    """Connect to the live Plex server."""
    plex = await get_plex_server()
    assert plex is not None


# ---------------------------------------------------------------------------
# Movies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_search_movies_title():
    result = await search_movies(title="Fast")
    assert isinstance(result, str)
    assert ("Result #" in result) or ("No movies found" in result)


@pytest.mark.asyncio
async def test_integration_search_movies_by_year():
    result = await search_movies(year=1999)
    assert isinstance(result, str)
    assert ("Result #" in result) or ("No movies found" in result)


@pytest.mark.asyncio
async def test_integration_search_movies_by_director():
    result = await search_movies(director="Christopher Nolan")
    assert isinstance(result, str)
    assert ("Result #" in result) or ("No movies found" in result)


@pytest.mark.asyncio
async def test_integration_search_movies_by_rating():
    """Content rating filter should work and results should show correct Rating field."""
    result = await search_movies(rating="R", limit=5)
    assert isinstance(result, str)
    if "Result #" in result:
        # Every result must show a Rating line (not None)
        for line in result.splitlines():
            if line.strip().startswith("Rating:"):
                assert "None" not in line, f"Rating field shows None: {line}"


@pytest.mark.asyncio
async def test_integration_search_movies_score_field():
    """Score field should show a numeric value, not N/A."""
    result = await search_movies(limit=5)
    assert isinstance(result, str)
    if "Result #" in result:
        score_lines = [l for l in result.splitlines() if l.strip().startswith("Score:")]
        assert score_lines, "No Score lines found in output"
        for line in score_lines:
            assert "N/A" not in line, f"Score is N/A: {line}"


@pytest.mark.asyncio
async def test_integration_search_movies_unwatched():
    result = await search_movies(watched=False)
    assert isinstance(result, str)
    assert ("Result #" in result) or ("No movies found" in result)


@pytest.mark.asyncio
async def test_integration_search_movies_min_duration():
    result = await search_movies(min_duration=120)
    assert isinstance(result, str)
    assert ("Result #" in result) or ("No movies found" in result)


@pytest.mark.asyncio
async def test_integration_get_movie_details():
    result = await search_movies(limit=1)
    key = _first_movie_key(result)
    assert key, "Could not extract movie key from search result"
    details = await get_movie_details(key)
    assert isinstance(details, str)
    assert "Title:" in details


@pytest.mark.asyncio
async def test_integration_get_movie_genres():
    result = await search_movies(limit=1)
    key = _first_movie_key(result)
    assert key
    genres = await get_movie_genres(key)
    assert isinstance(genres, str)


@pytest.mark.asyncio
async def test_integration_recent_movies():
    result = await recent_movies(count=5)
    assert isinstance(result, str)
    assert ("Recent Movie #" in result) or ("No recent movies" in result)


@pytest.mark.asyncio
async def test_integration_most_watched_movies():
    result = await most_watched(media_type="movies", count=5)
    assert isinstance(result, str)
    assert ("watched" in result) or ("No watched" in result)


@pytest.mark.asyncio
async def test_integration_most_watched_shows():
    result = await most_watched(media_type="shows", count=5)
    assert isinstance(result, str)
    assert ("watched" in result) or ("No watched" in result)


@pytest.mark.asyncio
async def test_integration_get_similar_movies():
    """get_similar_movies should return titles, not raise an error."""
    result = await search_movies(limit=1)
    key = _first_movie_key(result)
    assert key
    similar = await get_similar_movies(key, limit=5)
    assert isinstance(similar, str)
    # Should not contain a raw exception or error string
    assert "Failed" not in similar


# ---------------------------------------------------------------------------
# Watch activity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_get_watch_history():
    result = await get_watch_history(count=5)
    assert isinstance(result, str)
    assert ("No watch history" in result) or ("[Movie]" in result) or ("[Episode]" in result)


@pytest.mark.asyncio
async def test_integration_get_on_deck():
    result = await get_on_deck()
    assert isinstance(result, str)
    assert ("Nothing on deck" in result) or ("%" in result) or ("in progress" in result)


@pytest.mark.asyncio
async def test_integration_get_library_stats():
    result = await get_library_stats()
    assert isinstance(result, str)
    assert "Movies" in result
    assert "GB" in result


# ---------------------------------------------------------------------------
# TV Shows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_search_tv_shows():
    result = await search_tv_shows(limit=5)
    assert isinstance(result, str)
    assert ("seasons" in result) or ("No TV shows found" in result)


@pytest.mark.asyncio
async def test_integration_get_show_details():
    result = await search_tv_shows(limit=1)
    key = _first_key_from_result(result)
    assert key, "Could not extract show key from search result"
    details = await get_show_details(key)
    assert isinstance(details, str)
    assert "Title:" in details
    assert "Seasons:" in details


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_list_playlists():
    result = await list_playlists()
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integration_search_music():
    result = await search_music(artist="a", limit=5)
    assert isinstance(result, str)
    assert ("[key:" in result) or ("No music found" in result)


@pytest.mark.asyncio
async def test_integration_get_artist_details():
    result = await search_music(artist="a", limit=1)
    key = _first_key_from_result(result)
    assert key, "Could not extract artist key from search result"
    details = await get_artist_details(key)
    assert isinstance(details, str)
    assert "Artist:" in details
    assert "Albums" in details


@pytest.mark.asyncio
async def test_integration_get_similar_artists():
    result = await search_music(artist="a", limit=1)
    key = _first_key_from_result(result)
    assert key, "Could not extract artist key from search result"
    similar = await get_similar_artists(key, limit=5)
    assert isinstance(similar, str)
    assert "Failed" not in similar


@pytest.mark.asyncio
async def test_integration_get_album_details():
    result = await search_music(artist="a", limit=1)
    artist_key = _first_key_from_result(result)
    assert artist_key
    artist_details = await get_artist_details(artist_key)
    album_key = _first_key_from_result(artist_details)
    assert album_key, "Could not extract album key from artist details"
    details = await get_album_details(album_key)
    assert isinstance(details, str)
    assert "Album:" in details
    assert "Track listing:" in details

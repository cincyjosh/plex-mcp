import asyncio
import pytest
from unittest.mock import MagicMock
from datetime import datetime

# Module: Tests for plex_mcp module
# This file contains tests for the plex_mcp module functions, including edge cases,
# large datasets, and error handling.

# --- Import the Module Under Test ---
from plex_mcp import (
    MovieSearchParams,
    search_movies,
    get_movie_details,
    list_playlists,
    get_playlist_items,
    create_playlist,
    delete_playlist,
    add_to_playlist,
    recent_movies,
    get_movie_genres,
    most_watched,
    get_watch_history,
    get_on_deck,
    get_library_stats,
    search_tv_shows,
    get_show_details,
    get_similar_movies,
    get_similar_artists,
    search_music,
    get_artist_details,
    get_album_details,
)

# --- Set Dummy Environment Variables ---
@pytest.fixture(autouse=True)
def set_dummy_env(monkeypatch):
    monkeypatch.setenv("PLEX_SERVER_URL", "http://dummy")
    monkeypatch.setenv("PLEX_TOKEN", "dummy")

# --- Dummy Classes to Simulate Plex Objects ---

class DummyTag:
    def __init__(self, tag):
        self.tag = tag


class DummyMovie:
    def __init__(
        self,
        rating_key,
        title,
        year=2022,
        duration=120 * 60_000,  # in ms
        studio="Test Studio",
        summary="A test summary",
        content_rating="PG",
        rating=7.5,
        directors=None,
        roles=None,
        genres=None,
        type_="movie",
        addedAt=None,  # New parameter
    ):
        self.ratingKey = rating_key
        self.title = title
        self.year = year
        self.duration = duration
        self.studio = studio
        self.summary = summary
        self.contentRating = content_rating
        self.audienceRating = rating
        self.directors = [DummyTag(d) for d in (directors or [])]
        self.roles = [DummyTag(r) for r in (roles or [])]
        self.genres = [DummyTag(g) for g in (genres or [])]
        self.type = type_
        self.listType = "video"
        self.addedAt = addedAt  # New attribute

# Subclass for movies with genres.
class DummyMovieWithGenres(DummyMovie):
    def __init__(self, ratingKey, title, genres, **kwargs):
        super().__init__(ratingKey, title, **kwargs)
        self.genres = genres

class DummyGenre:
    def __init__(self, tag):
        self.tag = tag

class DummySection:
    def __init__(self, section_type, title="Movies"):
        self.type = section_type
        self.title = title

    def search(self, filters):
        # By default, if ratingKey equals 1, return a DummyMovie.
        if filters.get("ratingKey") == 1:
            return [DummyMovie(1, "Test Movie")]
        return []

    def recentlyAdded(self, maxresults):
        return []

class DummyMovieSection:
    def __init__(self, movies=None):
        self._movies = movies if movies is not None else []

    def search(self, title=None, maxresults=None, **kwargs):
        results = [m for m in self._movies if title is None or title.lower() in m.title.lower()]
        if maxresults is not None:
            results = results[:maxresults]
        return results

    def recentlyAdded(self, maxresults=None):
        results = list(self._movies)
        if maxresults is not None:
            results = results[:maxresults]
        return results

class DummyLibrary:
    def __init__(self, movies=None):
        self._movies = movies if movies is not None else []
        self._section = DummyMovieSection(movies)

    def search(self, **kwargs):
        title = kwargs.get("title")
        if isinstance(title, MovieSearchParams):
            title = title.title  # Unwrap if passed improperly
        if kwargs.get("libtype") == "movie":
            return [m for m in self._movies if title is None or title.lower() in m.title.lower()]
        return []

    def section(self, name):
        return self._section

    def sections(self):
        return [DummySection("movie")]

class DummyPlaylist:
    def __init__(self, ratingKey, title, items):
        self.ratingKey = ratingKey
        self.title = title
        self._items = items  # list of movies
        self.updatedAt = datetime(2022, 1, 1, 12, 0, 0)

    def items(self):
        return self._items

    def delete(self):
        pass

    def addItems(self, items):
        self._items.extend(items)

class DummyPlexServer:
    def __init__(self, movies=None, playlists=None):
        self._movies = movies if movies is not None else []
        self.library = DummyLibrary(movies)
        self._playlists = playlists if playlists is not None else []

    def fetchItem(self, key):
        from plexapi.exceptions import NotFound
        movie = next((m for m in self._movies if m.ratingKey == key), None)
        if movie is None:
            raise NotFound(f"No item with key {key}")
        return movie

    def playlists(self):
        return self._playlists

    def createPlaylist(self, name, items):
        new_playlist = DummyPlaylist(1, name, items)
        self._playlists.append(new_playlist)
        return new_playlist

# Asynchronous dummy_get_plex_server function.
async def dummy_get_plex_server(movies=None, playlists=None):
    await asyncio.sleep(0)
    return DummyPlexServer(movies, playlists)

# --- Fixtures ---

@pytest.fixture
def patch_get_plex_server(monkeypatch):
    """Fixture to patch the get_plex_server function with a dummy Plex server."""
    def _patch(movies=None, playlists=None):
        monkeypatch.setattr(
            "plex_mcp.plex_mcp.get_plex_server",
            lambda: dummy_get_plex_server(movies, playlists)
        )
    return _patch

@pytest.fixture
def dummy_movie():
    return DummyMovie(
        rating_key=1,
        title="Test Movie",
        year=2022,
        directors=["Jane Doe"],
        roles=["Test Actor"],
        genres=["Thriller"]
    )

# --- Tests for search_movies ---

@pytest.mark.asyncio
async def test_search_movies_found(patch_get_plex_server, dummy_movie):
    """Test that search_movies returns a formatted result when a movie is found."""
    patch_get_plex_server([dummy_movie])
    result = await search_movies(title="Test")
    assert "Test Movie" in result
    assert "more results" not in result

@pytest.mark.asyncio
async def test_search_movies_multiple_results(patch_get_plex_server):
    """Test that search_movies shows an extra results message when more than 5 movies are found."""
    movies = [DummyMovie(i, f"Test Movie {i}") for i in range(1, 8)]
    patch_get_plex_server(movies)
    result = await search_movies(title="Test")
    for i in range(1, 6):
        assert f"Test Movie {i}" in result
    assert "more results exist" in result

@pytest.mark.asyncio
async def test_search_movies_not_found(monkeypatch, patch_get_plex_server):
    """Test that search_movies returns a 'not found' message when no movies match the query."""
    patch_get_plex_server([])
    result = await search_movies(title="NonExisting")
    assert "No movies found" in result

@pytest.mark.asyncio
async def test_search_movies_exception(monkeypatch):
    """Test that search_movies raises PlexMCPError when an exception occurs."""
    from plex_mcp.plex_mcp import PlexMCPError
    dummy_server = DummyPlexServer([DummyMovie(1, "Test Movie")])
    dummy_server.library._section.search = MagicMock(side_effect=Exception("Search error"))

    async def mock_get_plex_server():
        return dummy_server

    monkeypatch.setattr("plex_mcp.plex_mcp.get_plex_server", mock_get_plex_server)

    with pytest.raises(PlexMCPError):
        await search_movies(title="Test")

@pytest.mark.asyncio
async def test_search_movies_empty_string(patch_get_plex_server):
    """Test search_movies with an empty string returns the not-found message."""
    patch_get_plex_server([])
    result = await search_movies(title="")
    assert result.startswith("No movies found")

@pytest.mark.asyncio
async def test_search_movies_none_input(patch_get_plex_server, dummy_movie):
    """Test that search_movies with None input returns results (treated as unfiltered search)."""
    patch_get_plex_server([dummy_movie])
    result = await search_movies()
    assert "Test Movie" in result

@pytest.mark.asyncio
async def test_search_movies_large_dataset(patch_get_plex_server):
    """Test that search_movies correctly handles a large dataset of movies."""
    movies = [DummyMovie(i, f"Test Movie {i}") for i in range(1, 201)]
    patch_get_plex_server(movies)
    result = await search_movies(title="Test")
    for i in range(1, 6):
        assert f"Test Movie {i}" in result
    assert "more results exist" in result

@pytest.mark.asyncio
async def test_search_movies_with_default_limit(patch_get_plex_server):
    """Test that search_movies respects the default limit of 5 results."""
    movies = [DummyMovie(i, f"Test Movie {i}") for i in range(1, 11)]
    patch_get_plex_server(movies)

    result = await search_movies(title="Test")
    assert "Result #1" in result
    assert "Result #5" in result
    assert "more results exist" in result
    assert "Result #6" not in result  # Ensure only 5 results are shown

@pytest.mark.asyncio
async def test_search_movies_with_custom_limit(patch_get_plex_server):
    """Test that search_movies respects a custom limit parameter."""
    # Mock the Plex library search to return 10 dummy movies
    movies = [DummyMovie(i, f"Test Movie {i}") for i in range(1, 11)]
    patch_get_plex_server(movies)

    result = await search_movies(title="Test", limit=8)
    assert "Result #1" in result
    assert "Result #8" in result
    assert "more results exist" in result
    assert "Result #9" not in result  # Ensure only 8 results are shown

@pytest.mark.asyncio
async def test_search_movies_with_limit_exceeding_results(patch_get_plex_server):
    """Test that search_movies handles a limit larger than the number of results."""
    movies = [DummyMovie(i, f"Test Movie {i}") for i in range(1, 4)]
    patch_get_plex_server(movies)

    result = await search_movies(title="Test", limit=10)
    assert "Result #1" in result
    assert "Result #3" in result
    assert "more results exist" not in result  # Ensure no "more results" message is shown
    assert "Result #4" not in result  # Ensure no extra results are shown

@pytest.mark.asyncio
async def test_search_movies_with_invalid_limit(patch_get_plex_server):
    """Test that search_movies handles an invalid limit (e.g., 0 or negative)."""
    # Mock the Plex library search to return 10 dummy movies
    movies = [DummyMovie(i, f"Test Movie {i}") for i in range(1, 11)]
    patch_get_plex_server(movies)

    result = await search_movies(title="Test", limit=0)
    assert "Result #1" in result
    assert "Result #2" not in result
    assert "more results exist" in result

@pytest.mark.asyncio
async def test_search_movies_no_results(patch_get_plex_server):
    """Test that search_movies returns an appropriate message when no results are found."""
    patch_get_plex_server([])

    result = await search_movies(title="Nonexistent")
    assert "No movies found" in result

# --- Tests for get_movie_details ---

@pytest.mark.asyncio
async def test_get_movie_details_valid(patch_get_plex_server, dummy_movie):
    """Test that get_movie_details returns a formatted movie string when a movie is found."""
    patch_get_plex_server([dummy_movie])
    result = await get_movie_details("1")
    assert "Test Movie" in result
    assert "2022" in result

@pytest.mark.asyncio
async def test_get_movie_details_invalid_key(patch_get_plex_server, dummy_movie):
    """Test that get_movie_details returns an error for a non-numeric movie key."""
    from plex_mcp.plex_mcp import PlexMCPError
    patch_get_plex_server([dummy_movie])
    with pytest.raises(PlexMCPError):
        await get_movie_details("invalid")

@pytest.mark.asyncio
async def test_get_movie_details_not_found(patch_get_plex_server):
    """Test that get_movie_details returns a 'not found' message when the movie is missing."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_get_plex_server([])

    with pytest.raises(PlexMCPNotFoundError):
        await get_movie_details("1")

# --- Tests for list_playlists ---

@pytest.mark.asyncio
async def test_list_playlists_empty(patch_get_plex_server):
    """Test that list_playlists returns a message when there are no playlists."""
    patch_get_plex_server(playlists=[])

    result = await list_playlists()
    assert "No playlists found" in result

@pytest.mark.asyncio
async def test_list_playlists_found(patch_get_plex_server, dummy_movie):
    """Test that list_playlists returns a formatted list when playlists exist."""
    dummy_playlist = DummyPlaylist(1, "My Playlist", [dummy_movie])
    patch_get_plex_server(playlists=[dummy_playlist])

    result = await list_playlists()
    assert "My Playlist" in result
    assert "Playlist #1" in result

# --- Tests for get_playlist_items ---

@pytest.mark.asyncio
async def test_get_playlist_items_found(patch_get_plex_server, dummy_movie):
    """Test that get_playlist_items returns the items of a found playlist."""
    dummy_playlist = DummyPlaylist(2, "My Playlist", [dummy_movie])
    patch_get_plex_server(playlists=[dummy_playlist])

    result = await get_playlist_items("2")
    assert "Test Movie" in result

@pytest.mark.asyncio
async def test_get_playlist_items_not_found(patch_get_plex_server):
    """Test that get_playlist_items returns an error when the playlist is not found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_get_plex_server(playlists=[])

    with pytest.raises(PlexMCPNotFoundError):
        await get_playlist_items("99")

@pytest.mark.asyncio
async def test_get_playlist_items_with_track(patch_plex_extended):
    """Test that get_playlist_items formats track items with artist, album, duration, and key."""
    track = DummyTrack(42, "Come Together", duration_ms=259000, track_number=1,
                       parent_title="Abbey Road", grandparent_title="The Beatles")
    dummy_playlist = DummyPlaylist(2, "My Music", [track])
    patch_plex_extended(tracks=[track])
    # Manually wire the playlist into patch_plex_extended via extended server
    from unittest.mock import AsyncMock, MagicMock, patch as mock_patch
    from plex_mcp import plex_mcp as module

    dummy_server = MagicMock()
    dummy_server.fetchItem.return_value = dummy_playlist
    dummy_server.playlists.return_value = [dummy_playlist]

    async def fake_get_plex():
        return dummy_server

    with mock_patch.object(module, "get_plex_server", fake_get_plex):
        result = await get_playlist_items("2")

    assert "Come Together" in result
    assert "The Beatles" in result
    assert "Abbey Road" in result
    assert "[key: 42]" in result

# --- Tests for create_playlist ---

@pytest.mark.asyncio
async def test_create_playlist_success(patch_get_plex_server, dummy_movie):
    """Test that create_playlist returns a success message on valid input."""
    patch_get_plex_server([dummy_movie])

    result = await create_playlist("My Playlist", "1")
    assert "Successfully created playlist 'My Playlist'" in result

@pytest.mark.asyncio
async def test_create_playlist_with_tracks(patch_plex_extended):
    """Test that create_playlist works with individual track keys."""
    track1 = DummyTrack(101, "Come Together", parent_title="Abbey Road", grandparent_title="The Beatles")
    track2 = DummyTrack(102, "Something", parent_title="Abbey Road", grandparent_title="The Beatles")
    patch_plex_extended(tracks=[track1, track2])
    result = await create_playlist("Beatles Mix", "101,102")
    assert "Successfully created playlist 'Beatles Mix'" in result
    assert "2 item(s)" in result

@pytest.mark.asyncio
async def test_create_playlist_mixed_types_rejected(patch_plex_extended):
    """Test that create_playlist rejects mixed audio/video items."""
    from plex_mcp.plex_mcp import PlexMCPError
    movie = DummyMovie(1, "Some Movie")
    track = DummyTrack(101, "Some Track")
    patch_plex_extended(movies=[movie], tracks=[track])
    with pytest.raises(PlexMCPError, match="Cannot mix media types"):
        await create_playlist("Bad Mix", "1,101")

@pytest.mark.asyncio
async def test_create_playlist_unknown_list_type_allowed(patch_plex_extended):
    """Test that create_playlist allows items where listType is None (unknown type)."""
    movie = DummyMovie(1, "Some Movie")
    movie.listType = None  # simulate missing listType
    patch_plex_extended(movies=[movie])
    result = await create_playlist("Uncertain Mix", "1")
    assert "Successfully created playlist" in result

@pytest.mark.asyncio
async def test_create_playlist_no_valid_items(patch_get_plex_server):
    """Test that create_playlist returns an error when no valid item keys are found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_get_plex_server([])

    with pytest.raises(PlexMCPNotFoundError):
        await create_playlist("My Playlist", "1,2")

# --- Tests for delete_playlist ---

@pytest.mark.asyncio
async def test_delete_playlist_success(patch_get_plex_server, dummy_movie):
    """Test that delete_playlist returns a success message when deletion is successful."""
    dummy_playlist = DummyPlaylist(3, "Delete Me", [dummy_movie])
    patch_get_plex_server(playlists=[dummy_playlist])

    result = await delete_playlist("3")
    assert "Successfully deleted playlist" in result

@pytest.mark.asyncio
async def test_delete_playlist_not_found(patch_get_plex_server):
    """Test that delete_playlist returns an error when no matching playlist is found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_get_plex_server(playlists=[])

    with pytest.raises(PlexMCPNotFoundError):
        await delete_playlist("99")

# --- Tests for add_to_playlist ---

@pytest.mark.asyncio
async def test_add_to_playlist_success(patch_get_plex_server):
    """Test that add_to_playlist returns a success message when an item is added."""
    dummy_playlist = DummyPlaylist(4, "My Playlist", [])
    dummy_movie = DummyMovie(5, "Added Movie")
    patch_get_plex_server([dummy_movie], playlists=[dummy_playlist])

    result = await add_to_playlist("4", "5")
    assert "Successfully added 'Added Movie' to playlist" in result

@pytest.mark.asyncio
async def test_add_to_playlist_playlist_not_found(patch_get_plex_server):
    """Test that add_to_playlist returns an error when the specified playlist is not found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_get_plex_server(playlists=[])

    with pytest.raises(PlexMCPNotFoundError):
        await add_to_playlist("999", "5")

# --- Tests for recent_movies ---

@pytest.mark.asyncio
async def test_recent_movies_found(patch_get_plex_server):
    """Test that recent_movies returns recent movie information when available."""
    recent_movie = DummyMovie(1, "Recent Movie", addedAt=datetime(2022, 5, 1))
    patch_get_plex_server([recent_movie])

    result = await recent_movies(5)
    assert "Recent Movie" in result

@pytest.mark.asyncio
async def test_recent_movies_not_found(patch_get_plex_server):
    """Test that recent_movies returns an error message when no recent movies are found."""
    patch_get_plex_server([])

    result = await recent_movies(5)
    assert "No recent movies found" in result

# --- Tests for get_movie_genres ---

@pytest.mark.asyncio
async def test_get_movie_genres_found(monkeypatch, patch_get_plex_server):
    """Test that get_movie_genres returns the correct genres for a movie."""
    # Create a dummy movie with genre tags
    movie_with_genres = DummyMovie(
        rating_key=1,
        title="Test Movie",
        genres=["Action", "Thriller"]
    )

    patch_get_plex_server([movie_with_genres])
    result = await get_movie_genres("1")
    assert "Action" in result
    assert "Thriller" in result

@pytest.mark.asyncio
async def test_get_movie_genres_not_found(patch_get_plex_server):
    """Test that get_movie_genres returns an error message when no matching movie is found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_get_plex_server([])
    with pytest.raises(PlexMCPNotFoundError):
        await get_movie_genres("1")


# --- Dummy Classes for New Tools ---

class DummyShow:
    def __init__(self, rating_key, title, year=2020, summary="A test show", genres=None,
                 roles=None, studio="Test Network", rating="TV-MA", child_count=2, leaf_count=20):
        self.ratingKey = rating_key
        self.title = title
        self.year = year
        self.summary = summary
        self.genres = [DummyTag(g) for g in (genres or ["Drama"])]
        self.roles = [DummyTag(r) for r in (roles or ["Actor One"])]
        self.studio = studio
        self.rating = rating
        self.childCount = child_count
        self.leafCount = leaf_count
        self.type = "show"

    def seasons(self):
        return [DummySeason(10, f"Season {i}", i, 10) for i in range(1, self.childCount + 1)]


class DummySeason:
    def __init__(self, rating_key, title, season_number, leaf_count):
        self.ratingKey = rating_key
        self.title = title
        self.seasonNumber = season_number
        self.leafCount = leaf_count


class DummyArtist:
    def __init__(self, rating_key, title, genres=None, summary="An artist", child_count=3):
        self.ratingKey = rating_key
        self.title = title
        self.genres = [DummyTag(g) for g in (genres or ["Rock"])]
        self.summary = summary
        self.childCount = child_count
        self.type = "artist"

    def albums(self):
        return [DummyAlbum(20 + i, f"Album {i}", self.title, year=2000 + i) for i in range(1, self.childCount + 1)]


class DummyTrack:
    def __init__(self, rating_key, title, duration_ms=240000, track_number=1,
                 parent_title="Album", grandparent_title="Artist"):
        self.ratingKey = rating_key
        self.title = title
        self.duration = duration_ms
        self.trackNumber = track_number
        self.parentTitle = parent_title
        self.grandparentTitle = grandparent_title
        self.type = "track"
        self.listType = "audio"


class DummyAlbum:
    def __init__(self, rating_key, title, parent_title="Artist", year=2020,
                 genres=None, leaf_count=10):
        self.ratingKey = rating_key
        self.title = title
        self.parentTitle = parent_title
        self.year = year
        self.genres = [DummyTag(g) for g in (genres or ["Rock"])]
        self.leafCount = leaf_count
        self.type = "album"

    def tracks(self):
        return [DummyTrack(100 + i, f"Track {i}", track_number=i, parent_title=self.title,
                           grandparent_title=self.parentTitle) for i in range(1, self.leafCount + 1)]


class DummyHistoryItem:
    def __init__(self, rating_key, title, item_type="movie", viewed_at=None, grandparent_title=None):
        self.ratingKey = rating_key
        self.title = title
        self.type = item_type
        self.viewedAt = viewed_at or datetime(2024, 1, 15, 20, 0)
        self.grandparentTitle = grandparent_title


class DummyOnDeckItem:
    def __init__(self, rating_key, title, item_type="movie", duration=7200000,
                 view_offset=3600000, grandparent_title=None):
        self.ratingKey = rating_key
        self.title = title
        self.type = item_type
        self.duration = duration
        self.viewOffset = view_offset
        self.grandparentTitle = grandparent_title


class DummyMediaPart:
    def __init__(self, size):
        self.size = size


class DummyMedia:
    def __init__(self, size):
        self.parts = [DummyMediaPart(size)]


class DummyMovieWithMedia(DummyMovie):
    def __init__(self, rating_key, title, size=1_073_741_824, **kwargs):
        super().__init__(rating_key, title, **kwargs)
        self.media = [DummyMedia(size)]


class DummyMusicSection:
    def __init__(self, artists=None, albums=None, tracks=None):
        self._artists = artists or []
        self._albums = albums or []
        self._tracks = tracks or []
        self.title = "Music"
        self.type = "artist"

    def searchArtists(self, maxresults=None, **kwargs):
        results = list(self._artists)
        title = kwargs.get("title")
        if title:
            results = [a for a in results if title.lower() in a.title.lower()]
        return results[:maxresults] if maxresults else results

    def searchAlbums(self, maxresults=None, **kwargs):
        results = list(self._albums)
        title = kwargs.get("title")
        if title:
            results = [a for a in results if title.lower() in a.title.lower()]
        return results[:maxresults] if maxresults else results

    def searchTracks(self, maxresults=None, **kwargs):
        results = list(self._tracks)
        title = kwargs.get("title")
        if title:
            results = [t for t in results if title.lower() in t.title.lower()]
        return results[:maxresults] if maxresults else results

    def all(self):
        return self._artists


class DummyShowSection:
    def __init__(self, shows=None):
        self._shows = shows or []
        self.title = "TV Shows"
        self.type = "show"

    def search(self, maxresults=None, **kwargs):
        results = list(self._shows)
        title = kwargs.get("title")
        if title:
            results = [s for s in results if title.lower() in s.title.lower()]
        return results[:maxresults] if maxresults else results

    def all(self):
        return self._shows


class DummyPlexServerExtended(DummyPlexServer):
    """Extended dummy server supporting shows, music, history, and on-deck."""

    def __init__(self, movies=None, playlists=None, shows=None, artists=None,
                 albums=None, tracks=None, history=None, on_deck=None):
        super().__init__(movies, playlists)
        self._shows = shows or []
        self._artists = artists or []
        self._albums = albums or []
        self._tracks = tracks or []
        self._history = history or []
        self._on_deck = on_deck or []
        self.library = DummyLibraryExtended(
            movies=movies, shows=shows, artists=artists, albums=albums, tracks=tracks,
            on_deck=on_deck,
        )

    def fetchItem(self, key):
        from plexapi.exceptions import NotFound
        all_items = (
            (self._movies or []) + self._shows + self._artists +
            self._albums + self._tracks
        )
        item = next((i for i in all_items if i.ratingKey == key), None)
        if item is None:
            raise NotFound(f"No item with key {key}")
        return item

    def myPlexAccount(self):
        return type("PlexAccount", (), {"username": "testuser"})()

    def systemAccounts(self):
        return [type("Account", (), {"id": 1, "name": "testuser"})()]

    def history(self, maxresults=None, accountID=None):
        return self._history[:maxresults] if maxresults else self._history


class DummyLibraryExtended(DummyLibrary):
    def __init__(self, movies=None, shows=None, artists=None, albums=None, tracks=None,
                 on_deck=None):
        super().__init__(movies)
        self._shows = shows or []
        self._artists = artists or []
        self._albums = albums or []
        self._tracks = tracks or []
        self._on_deck = on_deck or []
        self._show_section = DummyShowSection(shows)
        self._music_section = DummyMusicSection(artists, albums, tracks)

    def section(self, name):
        if name == "TV Shows":
            return self._show_section
        if name == "Music":
            return self._music_section
        return self._section

    def sections(self):
        sections = []
        if self._movies:
            s = DummyMovieSection(self._movies)
            s.title = "Movies"
            s.type = "movie"
            s.all = lambda: self._movies
            sections.append(s)
        if self._shows:
            s = self._show_section
            s.all = lambda: self._shows
            sections.append(s)
        if self._artists:
            s = self._music_section
            s.all = lambda: self._artists
            sections.append(s)
        return sections

    def onDeck(self):
        return []


@pytest.fixture
def patch_plex_extended(monkeypatch):
    """Fixture to patch get_plex_server with DummyPlexServerExtended."""
    def _patch(movies=None, playlists=None, shows=None, artists=None,
               albums=None, tracks=None, history=None, on_deck=None):
        server = DummyPlexServerExtended(
            movies=movies, playlists=playlists, shows=shows,
            artists=artists, albums=albums, tracks=tracks,
            history=history, on_deck=on_deck,
        )

        async def mock_server():
            return server

        monkeypatch.setattr("plex_mcp.plex_mcp.get_plex_server", mock_server)
        return server

    return _patch


# --- Tests for most_watched ---

@pytest.mark.asyncio
async def test_most_watched_movies(patch_plex_extended):
    """Test most_watched returns movies sorted by view count."""
    movie1 = DummyMovie(1, "Popular Movie")
    movie1.viewCount = 10
    movie2 = DummyMovie(2, "Less Popular")
    movie2.viewCount = 3
    patch_plex_extended(movies=[movie1, movie2])
    result = await most_watched(media_type="movies", count=5)
    assert "Popular Movie" in result
    assert "Less Popular" in result


@pytest.mark.asyncio
async def test_most_watched_invalid_type(patch_plex_extended):
    """Test most_watched returns error for invalid media_type."""
    from plex_mcp.plex_mcp import PlexMCPError
    patch_plex_extended()
    with pytest.raises(PlexMCPError):
        await most_watched(media_type="podcasts")


@pytest.mark.asyncio
async def test_most_watched_invalid_count(patch_plex_extended):
    """Test most_watched returns error for non-positive count."""
    from plex_mcp.plex_mcp import PlexMCPError
    patch_plex_extended()
    with pytest.raises(PlexMCPError):
        await most_watched(count=0)


# --- Tests for get_watch_history ---

@pytest.mark.asyncio
async def test_get_watch_history_found(patch_plex_extended):
    """Test get_watch_history returns recently watched items."""
    history = [
        DummyHistoryItem(1, "Watched Movie", item_type="movie"),
        DummyHistoryItem(2, "Episode Title", item_type="episode", grandparent_title="My Show"),
    ]
    patch_plex_extended(history=history)
    result = await get_watch_history(count=10)
    assert "Watched Movie" in result
    assert "My Show" in result
    assert "Episode Title" in result


@pytest.mark.asyncio
async def test_get_watch_history_empty(patch_plex_extended):
    """Test get_watch_history returns appropriate message when history is empty."""
    patch_plex_extended(history=[])
    result = await get_watch_history()
    assert "No watch history found" in result


@pytest.mark.asyncio
async def test_get_watch_history_invalid_count(patch_plex_extended):
    """Test get_watch_history returns error for non-positive count."""
    from plex_mcp.plex_mcp import PlexMCPError
    patch_plex_extended()
    with pytest.raises(PlexMCPError):
        await get_watch_history(count=0)


@pytest.mark.asyncio
async def test_get_watch_history_unresolvable_account(patch_plex_extended):
    """Test get_watch_history raises error when account ID cannot be resolved."""
    from plex_mcp.plex_mcp import PlexMCPError

    # Patch the server so the authenticated username doesn't match any system account.
    server = patch_plex_extended(history=[])
    server.myPlexAccount = lambda: type("Acct", (), {"username": "ghost"})()
    server.systemAccounts = lambda: [type("SA", (), {"id": 1, "name": "someone_else"})()]

    with pytest.raises(PlexMCPError, match="Could not resolve the authenticated user account"):
        await get_watch_history()


# --- Tests for get_on_deck ---

@pytest.mark.asyncio
async def test_get_on_deck_empty(patch_plex_extended):
    """Test get_on_deck returns message when nothing is in progress."""
    patch_plex_extended()
    result = await get_on_deck()
    assert "Nothing on deck" in result


@pytest.mark.asyncio
async def test_get_on_deck_with_items(monkeypatch):
    """Test get_on_deck returns in-progress items with percentage."""
    on_deck_items = [
        DummyOnDeckItem(1, "Half Done Movie", duration=7200000, view_offset=3600000),
    ]
    server = DummyPlexServerExtended()

    async def mock_server():
        return server

    server.library.onDeck = lambda: on_deck_items
    monkeypatch.setattr("plex_mcp.plex_mcp.get_plex_server", mock_server)

    result = await get_on_deck()
    assert "Half Done Movie" in result
    assert "50%" in result


# --- Tests for get_library_stats ---

@pytest.mark.asyncio
async def test_get_library_stats_with_movies(patch_plex_extended):
    """Test get_library_stats returns stats for movie library."""
    movies = [DummyMovieWithMedia(1, "Movie A", size=2_147_483_648, duration=7200000)]
    patch_plex_extended(movies=movies)
    result = await get_library_stats()
    assert "Movies" in result or "movie" in result.lower()
    assert "1 items" in result


@pytest.mark.asyncio
async def test_get_library_stats_empty(monkeypatch):
    """Test get_library_stats returns message when no sections exist."""
    server = DummyPlexServerExtended()
    server.library.sections = lambda: []

    async def mock_server():
        return server

    monkeypatch.setattr("plex_mcp.plex_mcp.get_plex_server", mock_server)
    result = await get_library_stats()
    assert "No library sections found" in result


# --- Tests for search_tv_shows ---

@pytest.mark.asyncio
async def test_search_tv_shows_found(patch_plex_extended):
    """Test search_tv_shows returns matching shows."""
    shows = [DummyShow(1, "Breaking Bad", year=2008, genres=["Drama", "Crime"])]
    patch_plex_extended(shows=shows)
    result = await search_tv_shows(title="Breaking")
    assert "Breaking Bad" in result
    assert "2008" in result


@pytest.mark.asyncio
async def test_search_tv_shows_not_found(patch_plex_extended):
    """Test search_tv_shows returns message when no shows match."""
    patch_plex_extended(shows=[])
    result = await search_tv_shows(title="Nonexistent Show")
    assert "No TV shows found" in result


@pytest.mark.asyncio
async def test_search_tv_shows_limit(patch_plex_extended):
    """Test search_tv_shows respects the limit parameter."""
    shows = [DummyShow(i, f"Show {i}") for i in range(1, 10)]
    patch_plex_extended(shows=shows)
    result = await search_tv_shows(limit=3)
    assert "Show 1" in result
    assert "more results exist" in result


# --- Tests for get_show_details ---

@pytest.mark.asyncio
async def test_get_show_details_found(patch_plex_extended):
    """Test get_show_details returns show info and seasons."""
    show = DummyShow(1, "Test Show", child_count=3)
    patch_plex_extended(shows=[show])
    result = await get_show_details("1")
    assert "Test Show" in result
    assert "Season 1" in result
    assert "Season 2" in result


@pytest.mark.asyncio
async def test_get_show_details_not_found(patch_plex_extended):
    """Test get_show_details returns error when show key not found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_plex_extended(shows=[])
    with pytest.raises(PlexMCPNotFoundError):
        await get_show_details("999")


# --- Tests for get_similar_movies ---

@pytest.mark.asyncio
async def test_get_similar_movies_none(patch_plex_extended):
    """Test get_similar_movies returns message when no similar movies exist."""
    movie = DummyMovie(1, "Lone Movie")
    movie.similar = []
    patch_plex_extended(movies=[movie])
    result = await get_similar_movies("1")
    assert "No similar movies found" in result


@pytest.mark.asyncio
async def test_get_similar_movies_found(patch_plex_extended):
    """Test get_similar_movies returns related movies."""
    movie = DummyMovie(1, "Base Movie")
    movie.similar = [DummyGenre("Similar Movie A"), DummyGenre("Similar Movie B")]
    patch_plex_extended(movies=[movie])
    result = await get_similar_movies("1")
    assert "Similar Movie A" in result
    assert "Similar Movie B" in result


@pytest.mark.asyncio
async def test_get_similar_movies_not_found(patch_plex_extended):
    """Test get_similar_movies returns error when movie key not found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_plex_extended(movies=[])
    with pytest.raises(PlexMCPNotFoundError):
        await get_similar_movies("999")


# --- Tests for get_similar_artists ---

@pytest.mark.asyncio
async def test_get_similar_artists_none(patch_plex_extended):
    """Test get_similar_artists returns message when no similar artists exist."""
    artist = DummyArtist(1, "Lone Artist")
    artist.similar = []
    patch_plex_extended(artists=[artist])
    result = await get_similar_artists("1")
    assert "No similar artists found" in result


@pytest.mark.asyncio
async def test_get_similar_artists_found(patch_plex_extended):
    """Test get_similar_artists returns related artists."""
    artist = DummyArtist(1, "Base Artist")
    artist.similar = [DummyGenre("Similar Artist A"), DummyGenre("Similar Artist B")]
    patch_plex_extended(artists=[artist])
    result = await get_similar_artists("1")
    assert "Similar Artist A" in result
    assert "Similar Artist B" in result


@pytest.mark.asyncio
async def test_get_similar_artists_not_found(patch_plex_extended):
    """Test get_similar_artists raises error when artist key not found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_plex_extended(artists=[])
    with pytest.raises(PlexMCPNotFoundError):
        await get_similar_artists("999")


# --- Tests for search_music ---

@pytest.mark.asyncio
async def test_search_music_by_artist(patch_plex_extended):
    """Test search_music finds artists by name."""
    artists = [DummyArtist(1, "The Beatles", genres=["Rock"])]
    patch_plex_extended(artists=artists)
    result = await search_music(artist="Beatles")
    assert "The Beatles" in result
    assert "Rock" in result


@pytest.mark.asyncio
async def test_search_music_by_album(patch_plex_extended):
    """Test search_music finds albums by title."""
    albums = [DummyAlbum(1, "Abbey Road", parent_title="The Beatles", year=1969)]
    patch_plex_extended(albums=albums)
    result = await search_music(album="Abbey Road")
    assert "Abbey Road" in result
    assert "1969" in result


@pytest.mark.asyncio
async def test_search_music_by_track(patch_plex_extended):
    """Test search_music finds tracks by title."""
    tracks = [DummyTrack(1, "Come Together", parent_title="Abbey Road",
                         grandparent_title="The Beatles")]
    patch_plex_extended(tracks=tracks)
    result = await search_music(track="Come Together")
    assert "Come Together" in result
    assert "The Beatles" in result


@pytest.mark.asyncio
async def test_search_music_no_params(patch_plex_extended):
    """Test search_music returns error when no search params given."""
    from plex_mcp.plex_mcp import PlexMCPError
    patch_plex_extended()
    with pytest.raises(PlexMCPError):
        await search_music()


@pytest.mark.asyncio
async def test_search_music_not_found(patch_plex_extended):
    """Test search_music returns message when no results found."""
    patch_plex_extended(artists=[])
    result = await search_music(artist="Nonexistent Artist")
    assert "No music found" in result


# --- Tests for get_artist_details ---

@pytest.mark.asyncio
async def test_get_artist_details_found(patch_plex_extended):
    """Test get_artist_details returns artist info and albums."""
    artist = DummyArtist(1, "The Beatles", genres=["Rock"], child_count=3)
    patch_plex_extended(artists=[artist])
    result = await get_artist_details("1")
    assert "The Beatles" in result
    assert "Rock" in result
    assert "Album 1" in result


@pytest.mark.asyncio
async def test_get_artist_details_not_found(patch_plex_extended):
    """Test get_artist_details returns error when artist not found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_plex_extended(artists=[])
    with pytest.raises(PlexMCPNotFoundError):
        await get_artist_details("999")


# --- Tests for get_album_details ---

@pytest.mark.asyncio
async def test_get_album_details_found(patch_plex_extended):
    """Test get_album_details returns album info and track listing with keys."""
    album = DummyAlbum(1, "Abbey Road", parent_title="The Beatles", year=1969, leaf_count=5)
    patch_plex_extended(albums=[album])
    result = await get_album_details("1")
    assert "Abbey Road" in result
    assert "The Beatles" in result
    assert "1969" in result
    assert "Track 1" in result
    assert "[key:" in result


@pytest.mark.asyncio
async def test_get_album_details_not_found(patch_plex_extended):
    """Test get_album_details returns error when album not found."""
    from plex_mcp.plex_mcp import PlexMCPNotFoundError
    patch_plex_extended(albums=[])
    with pytest.raises(PlexMCPNotFoundError):
        await get_album_details("999")

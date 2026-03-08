"""
Module: plex_mcp

This module provides tools for interacting with a Plex server via FastMCP.
It includes functions to search for movies, retrieve movie details, manage playlists,
and obtain recent movies and movie genres. Logging and asynchronous execution are used
to handle non-blocking I/O and to provide informative error logging.
"""

# --- Import Statements ---
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import os
import asyncio
import logging

from plexapi.server import PlexServer
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from mcp.server.fastmcp import FastMCP

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,  # Use DEBUG for more verbosity during development
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- FastMCP Server Initialization ---
mcp = FastMCP("plex")


class PlexMCPError(Exception):
    """Base class for all exceptions in this module."""

class PlexMCPConnectionError(PlexMCPError):
    """Raised when there is a connection error to the Plex server."""

class PlexMCPNotFoundError(PlexMCPError):
    """Raised when an item is not found in the Plex library."""


# --- Utility Formatting Functions ---

MAX_LIMIT: int = 50
MAX_COUNT: int = 50
MAX_KEYS: int = 100
MAX_STATS_LEAVES: int = 5_000  # Max leaf items (episodes/tracks) scanned per section in get_library_stats

DEFAULT_LIMIT: int = 5
DEFAULT_COUNT: int = 10
DEFAULT_MUSIC_LIMIT: int = 10


def clamp(value: Any, minimum: Any, maximum: Any) -> Any:
    """
    Clamp a value to a given range.
    """
    return max(minimum, min(value, maximum))


def clamp_int(value: Optional[int], default: int, minimum: int, maximum: int) -> int:
    """
    Clamp a numeric input to a safe range.
    """
    if value is None:
        return default
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return clamp(value, minimum, maximum)


def format_movie(movie: Any) -> str:
    """
    Format a movie object into a human-readable string.
    
    Parameters:
        movie: A Plex movie object.
        
    Returns:
        A formatted string containing movie details.
    """
    title = getattr(movie, 'title', 'Unknown Title')
    year = getattr(movie, 'year', 'Unknown Year')
    summary = getattr(movie, 'summary', 'No summary available')
    duration = getattr(movie, 'duration', 0) // 60000 if hasattr(movie, 'duration') else 0
    content_rating = getattr(movie, 'contentRating', 'Unrated')
    audience_rating = getattr(movie, 'audienceRating', None)
    studio = getattr(movie, 'studio', 'Unknown Studio')
    directors = [director.tag for director in getattr(movie, 'directors', [])[:3]]
    actors = [role.tag for role in getattr(movie, 'roles', [])[:5]]

    score_str = f"{audience_rating}/10" if audience_rating is not None else "N/A"
    return (
        f"Title: {title} ({year})\n"
        f"Rating: {content_rating}\n"
        f"Score: {score_str}\n"
        f"Duration: {duration} minutes\n"
        f"Studio: {studio}\n"
        f"Directors: {', '.join(directors) if directors else 'Unknown'}\n"
        f"Starring: {', '.join(actors) if actors else 'Unknown'}\n"
        f"Summary: {summary}\n"
    )

def format_playlist(playlist: Any, items: Optional[list] = None) -> str:
    """
    Format a playlist into a human-readable string.
    
    Parameters:
        playlist: A Plex playlist object.
        
    Returns:
        A formatted string containing playlist details.
    """
    if items is None:
        items = playlist.items()
    duration_mins = sum(item.duration for item in items) // 60000 if items else 0
    updated = (
        playlist.updatedAt.strftime('%Y-%m-%d %H:%M:%S')
        if hasattr(playlist, 'updatedAt') else 'Unknown'
    )
    return (
        f"Playlist: {playlist.title}\n"
        f"Items: {len(items)}\n"
        f"Duration: {duration_mins} minutes\n"
        f"Last Updated: {updated}\n"
    )

# --- Plex Client Class ---

class PlexClient:
    """
    Encapsulate the Plex connection logic.
    This class handles initialization and caching of the PlexServer instance.
    """
    def __init__(self, server_url: Optional[str] = None, token: Optional[str] = None) -> None:
        self.server_url = server_url or os.environ.get("PLEX_SERVER_URL", "").rstrip("/")
        self.token = token or os.environ.get("PLEX_TOKEN")
        
        if not self.server_url or not self.token:
            raise ValueError("Missing required configuration: Ensure PLEX_SERVER_URL and PLEX_TOKEN are set.")
        
        self._server = None

    def get_server(self) -> PlexServer:
        """
        Return a cached PlexServer instance, re-connecting if the cached instance is stale.

        Returns:
            A connected PlexServer instance.

        Raises:
            PlexMCPConnectionError: If connection initialization fails.
        """
        if self._server is not None:
            try:
                # Lightweight health check — raises if the connection is dead.
                self._server.library.sections()
                return self._server
            except Unauthorized:
                # Token revoked; do not retry — surface immediately.
                self._server = None
                logger.error("Unauthorized: Plex token is no longer valid.")
                raise PlexMCPConnectionError("Unauthorized: Invalid Plex token provided.")
            except Exception:
                # Any other error (network blip, server restart, etc.) — reconnect below.
                logger.warning("Plex server health check failed; attempting to reconnect.")
                self._server = None

        try:
            logger.info("Initializing PlexServer with URL: %s", self.server_url)
            self._server = PlexServer(self.server_url, self.token)
            logger.info("Successfully initialized PlexServer.")
            # Validate the new connection.
            self._server.library.sections()
            logger.info("Plex server connection validated.")
        except Unauthorized as exc:
            self._server = None
            logger.error("Unauthorized: Invalid Plex token provided.")
            raise PlexMCPConnectionError("Unauthorized: Invalid Plex token provided.") from exc
        except Exception as exc:
            self._server = None
            logger.exception("Error initializing Plex server: %s", exc)
            raise PlexMCPConnectionError(f"Error initializing Plex server: {exc}") from exc
        return self._server

# --- Data Classes ---

@dataclass
class MovieSearchParams:
    title:        Optional[str]  = None
    year:         Optional[int]  = None
    director:     Optional[str]  = None
    studio:       Optional[str]  = None
    genre:        Optional[str]  = None
    actor:        Optional[str]  = None
    rating:       Optional[str]  = None
    country:      Optional[str]  = None
    language:     Optional[str]  = None
    watched:      Optional[bool] = None   # True=only watched, False=only unwatched
    min_duration: Optional[int]  = None   # in minutes
    max_duration: Optional[int]  = None   # in minutes

    def to_filters(self) -> dict[str, Any]:
        # Simple equality filters mapped directly to section.search() kwargs
        FIELD_MAP = {
            "title":    "title",
            "year":     "year",
            "director": "director",
            "studio":   "studio",
            "genre":    "genre",
            "actor":    "actor",
            "rating":   "contentRating",
            "country":  "country",
            "language": "audioLanguage",
        }

        filters: Dict[str, Any] = {}

        for field_name, plex_arg in FIELD_MAP.items():
            value = getattr(self, field_name)
            if value is not None:
                filters[plex_arg] = value

        if self.watched is not None:
            # section.search() uses unwatched=True/False
            filters["unwatched"] = not self.watched

        # Duration: section.search() accepts duration>> / duration<< in milliseconds
        if self.min_duration is not None:
            filters["duration>>"] = self.min_duration * 60_000
        if self.max_duration is not None:
            filters["duration<<"] = self.max_duration * 60_000

        return filters


# --- Global Singleton and Access Functions ---

_plex_client_instance: PlexClient = None

def get_plex_client() -> PlexClient:
    """
    Return the singleton PlexClient instance, initializing it if necessary.
    
    Returns:
        A PlexClient instance.
    """
    global _plex_client_instance
    if _plex_client_instance is None:
        _plex_client_instance = PlexClient()
    return _plex_client_instance

async def get_plex_server() -> PlexServer:
    """
    Asynchronously get a PlexServer instance via the singleton PlexClient.
    
    Returns:
        A PlexServer instance.
        
    Raises:
        PlexMCPConnectionError: When the Plex server connection fails.
    """
    try:
        plex_client = get_plex_client()  # Singleton accessor
        plex = await asyncio.to_thread(plex_client.get_server)
        return plex
    except Exception as e:
        logger.exception("Failed to get Plex server instance")
        raise PlexMCPConnectionError("Failed to connect to Plex server") from e

# --- Tool Methods ---

@mcp.tool()
async def search_movies(
    title:        Optional[str]  = None,
    year:         Optional[int]  = None,
    director:     Optional[str]  = None,
    studio:       Optional[str]  = None,
    genre:        Optional[str]  = None,
    actor:        Optional[str]  = None,
    rating:       Optional[str]  = None,
    country:      Optional[str]  = None,
    language:     Optional[str]  = None,
    watched:      Optional[bool] = None,
    min_duration: Optional[int]  = None,
    max_duration: Optional[int]  = None,
    limit:        Optional[int]  = DEFAULT_LIMIT,
) -> str:
    """
    Search for movies in your Plex library using optional filters.
    
    Parameters:
        title: Optional title or substring to match.
        year: Optional release year to filter by.
        director: Optional director name to filter by.
        studio: Optional studio name to filter by.
        genre: Optional genre tag to filter by.
        actor: Optional actor name to filter by.
        rating: Optional rating (e.g., "PG-13") to filter by.
        country: Optional country of origin to filter by.
        language: Optional audio or subtitle language to filter by.
        watched: Optional boolean; True returns only watched movies, False only unwatched.
        min_duration: Optional minimum duration in minutes.
        max_duration: Optional maximum duration in minutes.
        
    Returns:
        A formatted string of up to 5 matching movies (with a count of any additional results).

    Raises:
        PlexMCPError: On unexpected failures.
        PlexMCPNotFoundError: When no movie library section exists.
    """

    # Validate the limit parameter
    limit = clamp_int(limit, default=5, minimum=1, maximum=MAX_LIMIT)

    params = MovieSearchParams(
        title, year, director, studio,
        genre, actor, rating, country,
        language, watched, min_duration, max_duration
    )
    filters = params.to_filters()
    logger.info("Searching Plex with filters: %r", filters)

    try:
        plex = await get_plex_server()
        try:
            movie_section = await asyncio.to_thread(lambda: plex.library.section("Movies"))
        except Exception:
            # Fall back to the first movie library if the name differs
            sections = await asyncio.to_thread(lambda: plex.library.sections())
            movie_section = next((s for s in sections if getattr(s, "type", None) == "movie"), None)
            if movie_section is None:
                raise PlexMCPNotFoundError("No movie library section found.")
        # Fetch one extra to detect if more results exist beyond the limit
        movies = await asyncio.to_thread(lambda: movie_section.search(maxresults=limit + 1, **filters))
    except PlexMCPConnectionError:
        raise
    except PlexMCPNotFoundError:
        raise
    except Exception as e:
        logger.exception("search_movies failed")
        raise PlexMCPError("Failed to search movies.") from e

    if not movies:
        return f"No movies found matching filters {filters!r}."

    has_more = len(movies) > limit
    display = movies[:limit]
    logger.info("Found %d movies (limit=%d) matching filters: %r", len(movies), limit, filters)

    results: List[str] = []
    for i, m in enumerate(display, start=1):
        results.append(f"Result #{i}:\nKey: {m.ratingKey}\n{format_movie(m)}")

    if has_more:
        results.append(f"\n... and more results exist. Increase limit to see more.")

    return "\n---\n".join(results)

@mcp.tool()
async def get_movie_details(movie_key: str) -> str:
    """
    Get detailed information about a specific movie.
    
    Parameters:
        movie_key: The key identifying the movie.
        
    Returns:
        A formatted string with movie details.

    Raises:
        PlexMCPError: On unexpected failures.
        PlexMCPNotFoundError: When the movie is not found.
    """
    try:
        plex = await get_plex_server()
        key = int(movie_key)
        movie = await asyncio.to_thread(plex.fetchItem, key)
        return format_movie(movie)
    except PlexMCPConnectionError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Movie with key {movie_key} not found.")
    except Exception as e:
        logger.exception("Failed to fetch movie details for key '%s'", movie_key)
        raise PlexMCPError("Failed to fetch movie details.") from e

@mcp.tool()
async def list_playlists() -> str:
    """
    List all playlists in the Plex server.
    
    Returns:
        A formatted string of playlists.

    Raises:
        PlexMCPError: On unexpected failures.
    """
    try:
        plex = await get_plex_server()
        playlists = await asyncio.to_thread(plex.playlists)
        if not playlists:
            return "No playlists found in your Plex server."
        formatted_playlists = []
        for i, playlist in enumerate(playlists, 1):
            items = await asyncio.to_thread(playlist.items)
            formatted_playlists.append(
                f"Playlist #{i}:\nKey: {playlist.ratingKey}\n{format_playlist(playlist, items=items)}"
            )
        return "\n---\n".join(formatted_playlists)
    except PlexMCPConnectionError:
        raise
    except Exception as e:
        logger.exception("Failed to fetch playlists")
        raise PlexMCPError("Failed to fetch playlists.") from e

@mcp.tool()
async def get_playlist_items(playlist_key: str) -> str:
    """
    Get the items in a specific playlist.
    
    Parameters:
        playlist_key: The key of the playlist to retrieve items from.
        
    Returns:
        A formatted string of playlist items.

    Raises:
        PlexMCPError: On unexpected failures.
        PlexMCPNotFoundError: When the playlist is not found.
    """
    try:
        plex = await get_plex_server()
        key = int(playlist_key)
        try:
            playlist = await asyncio.to_thread(plex.fetchItem, key)
        except NotFound:
            all_playlists = await asyncio.to_thread(plex.playlists)
            playlist = next((p for p in all_playlists if p.ratingKey == key), None)
            if not playlist:
                raise PlexMCPNotFoundError(f"No playlist found with key {playlist_key}.")

        items = await asyncio.to_thread(playlist.items)
        if not items:
            return "No items found in this playlist."

        formatted_items = []
        for i, item in enumerate(items, 1):
            item_type = getattr(item, 'type', 'unknown')
            if item_type == 'track':
                artist = getattr(item, 'grandparentTitle', 'Unknown Artist')
                album = getattr(item, 'parentTitle', 'Unknown Album')
                duration_s = (getattr(item, 'duration', 0) or 0) // 1000
                dur_str = f"{duration_s//60}:{duration_s%60:02d}"
                formatted_items.append(f"{i}. {item.title}  —  {artist} / {album}  ({dur_str})  [key: {item.ratingKey}]")
            elif item_type == 'episode':
                show = getattr(item, 'grandparentTitle', '')
                season = getattr(item, 'parentTitle', '')
                formatted_items.append(f"{i}. {show} — {season}: {item.title}  [key: {item.ratingKey}]")
            else:
                year = getattr(item, 'year', '')
                year_str = f" ({year})" if year else ""
                formatted_items.append(f"{i}. {item.title}{year_str}  [key: {item.ratingKey}]")
        return "\n".join(formatted_items)
    except PlexMCPConnectionError:
        raise
    except PlexMCPError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Playlist with key {playlist_key} not found.")
    except Exception as e:
        logger.exception("Failed to fetch items for playlist key '%s'", playlist_key)
        raise PlexMCPError("Failed to fetch playlist items.") from e

@mcp.tool()
async def create_playlist(name: str, item_keys: str) -> str:
    """
    Create a new playlist with specified media items.

    Works with any Plex media type: movies, tracks, episodes, etc.
    Use get_album_details() to find individual track keys for music playlists.

    Parameters:
        name: The desired name for the new playlist.
        item_keys: A comma-separated string of rating keys to include (movies, tracks, episodes).

    Returns:
        A success message with playlist details.

    Raises:
        PlexMCPError: On invalid input or unexpected failures.
        PlexMCPNotFoundError: When one or more item keys are not found.
    """
    try:
        plex = await get_plex_server()
        key_list = [int(key.strip()) for key in item_keys.split(",") if key.strip()]
        if not key_list:
            raise PlexMCPError("No valid item keys provided.")
        if len(key_list) > MAX_KEYS:
            raise PlexMCPError(f"Too many item keys. Max allowed is {MAX_KEYS}.")

        logger.info("Creating playlist '%s' with item keys: %s", name, item_keys)
        items = []
        not_found_keys = []

        for key in key_list:
            try:
                item = await asyncio.to_thread(plex.fetchItem, key)
                items.append(item)
                logger.info("Found item: %s (Key: %d)", item.title, key)
            except NotFound:
                not_found_keys.append(key)
                logger.warning("Could not find item with key: %d", key)

        if not_found_keys:
            raise PlexMCPNotFoundError(f"Some item keys were not found: {', '.join(str(k) for k in not_found_keys)}")
        if not items:
            raise PlexMCPError("No valid items found with the provided keys.")

        list_types = {getattr(item, 'listType', None) for item in items}
        known_types = {t for t in list_types if t is not None}
        if len(known_types) > 1:
            raise PlexMCPError(
                "Cannot mix media types in a playlist. "
                "All items must be the same type (all video or all audio)."
            )

        try:
            playlist = await asyncio.wait_for(
                asyncio.to_thread(lambda: plex.createPlaylist(name, items=items)),
                timeout=15.0,
            )
            logger.info("Playlist created successfully: %s", playlist.title)
            return f"Successfully created playlist '{name}' with {len(items)} item(s).\nPlaylist Key: {playlist.ratingKey}"
        except asyncio.TimeoutError:
            logger.warning("Playlist creation is taking longer than expected for '%s'", name)
            return ("PENDING: Playlist creation is taking longer than expected. "
                    "The operation might still complete in the background. "
                    "Please check your Plex server to confirm.")
    except PlexMCPConnectionError:
        raise
    except PlexMCPError:
        raise
    except ValueError as e:
        logger.error("Invalid input format for item keys: %s", e)
        raise PlexMCPError(f"Invalid input format. Please check item keys are valid numbers. {str(e)}") from e
    except Exception as e:
        logger.exception("Error creating playlist")
        raise PlexMCPError("Failed to create playlist.") from e

@mcp.tool()
async def delete_playlist(playlist_key: str) -> str:
    """
    Delete a playlist from the Plex server.
    
    Parameters:
        playlist_key: The key of the playlist to delete.
        
    Returns:
        A success message if deletion is successful.

    Raises:
        PlexMCPError: On unexpected failures.
        PlexMCPNotFoundError: When the playlist is not found.
    """
    try:
        plex = await get_plex_server()
        key = int(playlist_key)
        try:
            playlist = await asyncio.to_thread(plex.fetchItem, key)
        except NotFound:
            all_playlists = await asyncio.to_thread(plex.playlists)
            playlist = next((p for p in all_playlists if p.ratingKey == key), None)
            if not playlist:
                raise PlexMCPNotFoundError(f"No playlist found with key {playlist_key}.")
        await asyncio.to_thread(playlist.delete)
        logger.info("Playlist '%s' with key %s successfully deleted.", playlist.title, playlist_key)
        return f"Successfully deleted playlist '{playlist.title}' with key {playlist_key}."
    except PlexMCPConnectionError:
        raise
    except PlexMCPError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Playlist with key {playlist_key} not found.")
    except Exception as e:
        logger.exception("Failed to delete playlist with key '%s'", playlist_key)
        raise PlexMCPError("Failed to delete playlist.") from e

@mcp.tool()
async def add_to_playlist(playlist_key: str, item_key: str) -> str:
    """
    Add a media item to an existing playlist.

    Works with any Plex media type: movies, tracks, episodes, etc.
    Use get_album_details() to find individual track keys for adding music tracks.

    Parameters:
        playlist_key: The key of the playlist.
        item_key: The rating key of the item to add (movie, track, episode, etc.).

    Returns:
        A success message if the item is added.

    Raises:
        PlexMCPError: On invalid input or unexpected failures.
        PlexMCPNotFoundError: When the playlist or item is not found.
    """
    try:
        plex = await get_plex_server()
        p_key = int(playlist_key)
        i_key = int(item_key)

        # Find the playlist
        try:
            playlist = await asyncio.to_thread(plex.fetchItem, p_key)
        except NotFound:
            all_playlists = await asyncio.to_thread(plex.playlists)
            playlist = next((p for p in all_playlists if p.ratingKey == p_key), None)
            if not playlist:
                raise PlexMCPNotFoundError(f"No playlist found with key {playlist_key}.")

        try:
            item = await asyncio.to_thread(plex.fetchItem, i_key)
        except NotFound:
            raise PlexMCPNotFoundError(f"No item found with key {item_key}.")

        playlist_type = getattr(playlist, 'playlistType', None)
        item_list_type = getattr(item, 'listType', None)
        type_map = {"audio": "audio", "video": "video"}
        if playlist_type and item_list_type and type_map.get(item_list_type) != playlist_type:
            raise PlexMCPError(
                f"Cannot add a {item_list_type} item to a {playlist_type} playlist. "
                "Plex playlists cannot mix media types."
            )

        await asyncio.to_thread(lambda p=playlist, m=item: p.addItems([m]))
        logger.info("Added '%s' to playlist '%s'", item.title, playlist.title)
        return f"Successfully added '{item.title}' to playlist '{playlist.title}'."
    except PlexMCPConnectionError:
        raise
    except PlexMCPError:
        raise
    except ValueError:
        raise PlexMCPError("Invalid playlist or item key. Please provide valid numbers.")
    except Exception as e:
        logger.exception("Failed to add item to playlist")
        raise PlexMCPError("Failed to add item to playlist.") from e

@mcp.tool()
async def recent_movies(count: int = DEFAULT_LIMIT) -> str:
    """
    Get recently added movies from the Plex library.
    
    Parameters:
        count: The maximum number of recent movies to return.
        
    Returns:
        A formatted string of recent movies.

    Raises:
        PlexMCPError: On invalid input or unexpected failures.
    """
    if count <= 0:
        raise PlexMCPError("Count must be a positive integer.")
    if count > MAX_COUNT:
        count = MAX_COUNT
    
    try:
        plex = await get_plex_server()
        movie_section = await asyncio.to_thread(lambda: plex.library.section("Movies"))
        recent_movies_list = await asyncio.to_thread(lambda: movie_section.recentlyAdded(maxresults=count))

        if not recent_movies_list:
            return "No recent movies found in your Plex library."

        formatted_movies = []
        for i, movie in enumerate(recent_movies_list, 1):
            added_str = movie.addedAt.strftime('%Y-%m-%d') if getattr(movie, 'addedAt', None) else 'Unknown'
            formatted_movies.append(
                f"Recent Movie #{i}:\nKey: {movie.ratingKey}\nAdded: {added_str}\n{format_movie(movie)}"
            )
        return "\n---\n".join(formatted_movies)
    except PlexMCPConnectionError:
        raise
    except Exception as e:
        logger.exception("Failed to fetch recent movies")
        raise PlexMCPError("Failed to fetch recent movies.") from e

@mcp.tool()
async def get_movie_genres(movie_key: str) -> str:
    """
    Get genres for a specific movie.
    
    Parameters:
        movie_key: The key of the movie.
        
    Returns:
        A formatted string of movie genres.

    Raises:
        PlexMCPError: On invalid input or unexpected failures.
        PlexMCPNotFoundError: When the movie is not found.
    """
    try:
        plex = await get_plex_server()
        key = int(movie_key)
        movie = await asyncio.to_thread(plex.fetchItem, key)
        genres = [genre.tag for genre in movie.genres] if hasattr(movie, 'genres') else []
        if not genres:
            return f"No genres found for movie '{movie.title}'."
        return f"Genres for '{movie.title}':\n{', '.join(genres)}"
    except PlexMCPConnectionError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Movie with key {movie_key} not found.")
    except ValueError:
        raise PlexMCPError(f"Invalid movie key '{movie_key}'. Please provide a valid number.")
    except Exception as e:
        logger.exception("Failed to fetch genres for movie with key '%s'", movie_key)
        raise PlexMCPError("Failed to fetch movie genres.") from e

@mcp.tool()
async def most_watched(
    media_type: str = "movies",
    count: int = DEFAULT_COUNT,
) -> str:
    """
    Get the most watched movies or recently watched TV shows.

    Parameters:
        media_type: Either "movies" or "shows" (default: "movies").
        count: Number of results to return (default: 10).

    Returns:
        For movies: sorted by play count descending.
        For shows: sorted by last viewed date descending.
    """
    if media_type not in ("movies", "shows"):
        raise PlexMCPError("media_type must be 'movies' or 'shows'.")
    if count <= 0:
        raise PlexMCPError("count must be a positive integer.")
    if count > MAX_COUNT:
        count = MAX_COUNT

    try:
        plex = await get_plex_server()
        section_name = "Movies" if media_type == "movies" else "TV Shows"
        section = await asyncio.to_thread(lambda: plex.library.section(section_name))
        # viewCount sort is only valid for movies; shows use lastViewedAt
        sort = "viewCount:desc" if media_type == "movies" else "lastViewedAt:desc"
        all_items = await asyncio.to_thread(lambda: section.search(sort=sort, maxresults=count))

        if not all_items:
            return f"No watched {media_type} found."

        results = []
        for i, item in enumerate(all_items, 1):
            year = getattr(item, 'year', '')
            if media_type == "movies":
                view_count = getattr(item, 'viewCount', 0) or 0
                detail = f"watched {view_count}x"
            else:
                last_viewed = getattr(item, 'lastViewedAt', None)
                detail = f"last watched {last_viewed.strftime('%Y-%m-%d')}" if last_viewed else "watched"
            results.append(f"{i}. {item.title} ({year}) — {detail}  [key: {item.ratingKey}]")

        return "\n".join(results)
    except PlexMCPConnectionError:
        raise
    except Exception as e:
        logger.exception("Failed to fetch most watched %s", media_type)
        raise PlexMCPError(f"Failed to fetch most watched {media_type}.") from e


@mcp.tool()
async def get_watch_history(count: int = DEFAULT_COUNT) -> str:
    """
    Get recently played items across all libraries.

    Parameters:
        count: Number of history entries to return (default: 10).

    Returns:
        A formatted list of recently played media.
    """
    if count <= 0:
        raise PlexMCPError("count must be a positive integer.")
    if count > MAX_COUNT:
        count = MAX_COUNT

    try:
        plex = await get_plex_server()
        # Resolve the account ID for the token owner so history is scoped to
        # the authenticated user, not all shared accounts on the server.
        # myPlexUsername returns the email; myPlexAccount().username returns
        # the username that matches the systemAccounts name field.
        my_account = await asyncio.to_thread(lambda: plex.myPlexAccount())
        system_accounts = await asyncio.to_thread(lambda: plex.systemAccounts())
        account_id = next(
            (a.id for a in system_accounts if a.name == my_account.username), None
        )
        if account_id is None:
            raise PlexMCPError(
                "Could not resolve the authenticated user account. "
                "Watch history cannot be scoped to a single user."
            )
        history = await asyncio.to_thread(
            lambda: plex.history(maxresults=count, accountID=account_id)
        )
        if not history:
            return "No watch history found."

        results = []
        for i, item in enumerate(history, 1):
            title = getattr(item, 'title', 'Unknown')
            item_type = getattr(item, 'type', 'unknown').capitalize()
            viewed_at = getattr(item, 'viewedAt', None)
            viewed_str = viewed_at.strftime('%Y-%m-%d %H:%M') if viewed_at else 'Unknown'
            # For episodes, include show name
            grandparent = getattr(item, 'grandparentTitle', None)
            display = f"{grandparent} — {title}" if grandparent else title
            results.append(f"{i}. [{item_type}] {display}  (watched: {viewed_str})")

        return "\n".join(results)
    except PlexMCPConnectionError:
        raise
    except PlexMCPError:
        raise
    except Exception as e:
        logger.exception("Failed to fetch watch history")
        raise PlexMCPError("Failed to fetch watch history.") from e


@mcp.tool()
async def get_on_deck() -> str:
    """
    Get in-progress media items from Plex On Deck.

    Returns:
        A formatted list of items that are partially watched and ready to resume.
    """
    try:
        plex = await get_plex_server()
        on_deck = await asyncio.to_thread(lambda: plex.library.onDeck())
        if not on_deck:
            return "Nothing on deck."

        results = []
        for i, item in enumerate(on_deck, 1):
            title = getattr(item, 'title', 'Unknown')
            item_type = getattr(item, 'type', 'unknown').capitalize()
            grandparent = getattr(item, 'grandparentTitle', None)
            display = f"{grandparent} — {title}" if grandparent else title
            duration = getattr(item, 'duration', 0) or 0
            view_offset = getattr(item, 'viewOffset', 0) or 0
            if duration:
                pct = int(view_offset / duration * 100)
                progress = f"{pct}% through"
            else:
                progress = "in progress"
            results.append(f"{i}. [{item_type}] {display}  ({progress})  [key: {item.ratingKey}]")

        return "\n".join(results)
    except PlexMCPConnectionError:
        raise
    except Exception as e:
        logger.exception("Failed to fetch on deck")
        raise PlexMCPError("Failed to fetch on deck items.") from e


@mcp.tool()
async def get_library_stats() -> str:
    """
    Get summary statistics for all Plex libraries.

    Returns:
        Counts, total duration, and storage size per library section.
    """
    try:
        plex = await get_plex_server()
        sections = await asyncio.to_thread(lambda: plex.library.sections())
        if not sections:
            return "No library sections found."

        results = []
        for section in sections:
            items = await asyncio.to_thread(lambda s=section: s.all())
            count = len(items)

            # For TV and music, duration/size live on leaf nodes (episodes/tracks),
            # not on the parent show/artist objects — so we search for leaves directly.
            # Cap to MAX_STATS_LEAVES to avoid loading tens of thousands of items.
            if section.type in ("show", "artist"):
                search_fn = (
                    (lambda s=section: s.searchEpisodes(maxresults=MAX_STATS_LEAVES))
                    if section.type == "show"
                    else (lambda s=section: s.searchTracks(maxresults=MAX_STATS_LEAVES))
                )
                leaves = await asyncio.to_thread(search_fn)
            else:
                leaves = items

            total_ms = sum(getattr(leaf, 'duration', 0) or 0 for leaf in leaves)
            total_hours = total_ms // 3_600_000
            total_size = sum(
                sum(getattr(part, 'size', 0) or 0 for media in getattr(leaf, 'media', []) for part in getattr(media, 'parts', []))
                for leaf in leaves
            )
            size_gb = total_size / 1_073_741_824

            # count = top-level items (shows/artists/movies), leaf_count = episodes/tracks
            capped = len(leaves) == MAX_STATS_LEAVES and section.type in ("show", "artist")
            leaf_count = len(leaves) if section.type in ("show", "artist") else count
            cap_note = f" (capped at {MAX_STATS_LEAVES})" if capped else ""
            if section.type == "show":
                count_str = f"{count} shows, {leaf_count} episodes{cap_note}"
            elif section.type == "artist":
                count_str = f"{count} artists, {leaf_count} tracks{cap_note}"
            else:
                count_str = f"{count} items"

            results.append(
                f"{section.title} ({section.type}): {count_str}, "
                f"{total_hours}h total runtime, {size_gb:.1f} GB"
            )

        return "\n".join(results)
    except PlexMCPConnectionError:
        raise
    except Exception as e:
        logger.exception("Failed to fetch library stats")
        raise PlexMCPError("Failed to fetch library stats.") from e


@mcp.tool()
async def search_tv_shows(
    title: Optional[str] = None,
    year: Optional[int] = None,
    genre: Optional[str] = None,
    actor: Optional[str] = None,
    studio: Optional[str] = None,
    watched: Optional[bool] = None,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """
    Search for TV shows in the Plex library.

    Parameters:
        title: Optional title or substring to match.
        year: Optional release year.
        genre: Optional genre tag.
        actor: Optional actor name.
        studio: Optional studio/network name.
        watched: True for only watched, False for only unwatched.
        limit: Max results to return (default: 5).

    Returns:
        A formatted list of matching TV shows.
    """
    limit = clamp_int(limit, default=5, minimum=1, maximum=MAX_LIMIT)

    try:
        plex = await get_plex_server()
        section = await asyncio.to_thread(lambda: plex.library.section("TV Shows"))
        filters: Dict[str, Any] = {}
        if title:
            filters["title"] = title
        if year:
            filters["year"] = year
        if genre:
            filters["genre"] = genre
        if actor:
            filters["actor"] = actor
        if studio:
            filters["studio"] = studio
        if watched is not None:
            filters["unwatched"] = not watched

        shows = await asyncio.to_thread(lambda: section.search(maxresults=limit + 1, **filters))
        if not shows:
            return "No TV shows found matching those filters."

        has_more = len(shows) > limit
        results = []
        for i, show in enumerate(shows[:limit], 1):
            year_str = getattr(show, 'year', '')
            summary = getattr(show, 'summary', '')[:120]
            episode_count = getattr(show, 'leafCount', '?')
            season_count = getattr(show, 'childCount', '?')
            results.append(
                f"{i}. {show.title} ({year_str})  [key: {show.ratingKey}]\n"
                f"   {season_count} seasons, {episode_count} episodes\n"
                f"   {summary}{'...' if len(getattr(show, 'summary', '')) > 120 else ''}"
            )

        if has_more:
            results.append("\n... more results exist. Increase limit to see more.")

        return "\n\n".join(results)
    except PlexMCPConnectionError:
        raise
    except Exception as e:
        logger.exception("Failed to search TV shows")
        raise PlexMCPError("Failed to search TV shows.") from e


@mcp.tool()
async def get_show_details(show_key: str) -> str:
    """
    Get detailed information about a TV show including its seasons and episode counts.

    Parameters:
        show_key: The rating key of the TV show.

    Returns:
        Show details and a list of seasons.
    """
    try:
        plex = await get_plex_server()
        key = int(show_key)
        show = await asyncio.to_thread(plex.fetchItem, key)
        seasons = await asyncio.to_thread(show.seasons)

        genres = ", ".join(g.tag for g in getattr(show, 'genres', []))
        actors = ", ".join(r.tag for r in getattr(show, 'roles', [])[:5])
        summary = getattr(show, 'summary', 'No summary available.')
        rating = getattr(show, 'rating', 'Unrated')
        studio = getattr(show, 'studio', 'Unknown')

        lines = [
            f"Title: {show.title} ({getattr(show, 'year', '')})",
            f"Rating: {rating}",
            f"Studio/Network: {studio}",
            f"Genres: {genres or 'Unknown'}",
            f"Starring: {actors or 'Unknown'}",
            f"Summary: {summary}",
            "",
            "Seasons:",
        ]
        for season in seasons:
            ep_count = getattr(season, 'leafCount', '?')
            lines.append(f"  {season.title}: {ep_count} episodes  [key: {season.ratingKey}]")

        return "\n".join(lines)
    except PlexMCPConnectionError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Show with key {show_key} not found.")
    except Exception as e:
        logger.exception("Failed to fetch show details for key '%s'", show_key)
        raise PlexMCPError("Failed to fetch show details.") from e


@mcp.tool()
async def get_similar_movies(movie_key: str, limit: int = DEFAULT_LIMIT) -> str:
    """
    Get movies similar to a given movie based on Plex recommendations.

    Parameters:
        movie_key: The rating key of the movie.
        limit: Max number of similar movies to return (default: 5).

    Returns:
        A formatted list of similar movies.
    """
    try:
        plex = await get_plex_server()
        key = int(movie_key)
        movie = await asyncio.to_thread(plex.fetchItem, key)
        related = await asyncio.to_thread(lambda: movie.similar)

        if not related:
            return f"No similar movies found for '{movie.title}'."

        results = [f"Movies similar to '{movie.title}':\n"]
        limit = clamp_int(limit, default=5, minimum=1, maximum=MAX_LIMIT)
        for i, m in enumerate(related[:limit], 1):
            results.append(f"{i}. {getattr(m, 'title', getattr(m, 'tag', 'Unknown'))}")

        return "\n".join(results)
    except PlexMCPConnectionError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Movie with key {movie_key} not found.")
    except Exception as e:
        logger.exception("Failed to fetch similar movies for key '%s'", movie_key)
        raise PlexMCPError("Failed to fetch similar movies.") from e


@mcp.tool()
async def get_similar_artists(artist_key: str, limit: int = DEFAULT_LIMIT) -> str:
    """
    Get artists similar to a given artist based on Plex recommendations.

    Parameters:
        artist_key: The rating key of the artist.
        limit: Max number of similar artists to return (default: 5).

    Returns:
        A formatted list of similar artists.
    """
    try:
        plex = await get_plex_server()
        key = int(artist_key)
        artist = await asyncio.to_thread(plex.fetchItem, key)
        related = await asyncio.to_thread(lambda: artist.similar)

        if not related:
            return f"No similar artists found for '{artist.title}'."

        results = [f"Artists similar to '{artist.title}':\n"]
        limit = clamp_int(limit, default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT)
        for i, a in enumerate(related[:limit], 1):
            results.append(f"{i}. {getattr(a, 'title', getattr(a, 'tag', 'Unknown'))}")

        return "\n".join(results)
    except PlexMCPConnectionError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Artist with key {artist_key} not found.")
    except Exception as e:
        logger.exception("Failed to fetch similar artists for key '%s'", artist_key)
        raise PlexMCPError("Failed to fetch similar artists.") from e


@mcp.tool()
async def search_music(
    artist: Optional[str] = None,
    album: Optional[str] = None,
    track: Optional[str] = None,
    genre: Optional[str] = None,
    limit: int = DEFAULT_MUSIC_LIMIT,
) -> str:
    """
    Search for music in the Plex library by artist, album, track, or genre.

    Parameters:
        artist: Optional artist name to search for.
        album: Optional album title to search for.
        track: Optional track title to search for.
        genre: Optional genre to filter by.
        limit: Max results to return (default: 10).

    Returns:
        A formatted list of matching music items.
    """
    if not any([artist, album, track, genre]):
        raise PlexMCPError("Provide at least one search parameter (artist, album, track, or genre).")
    limit = clamp_int(limit, default=10, minimum=1, maximum=MAX_LIMIT)

    try:
        plex = await get_plex_server()
        section = await asyncio.to_thread(lambda: plex.library.section("Music"))
        results = []

        if track:
            filters: Dict[str, Any] = {"title": track}
            if genre:
                filters["genre"] = genre
            if artist:
                filters["artist.title"] = artist
            items = await asyncio.to_thread(lambda: section.searchTracks(maxresults=limit, **filters))
            for i, t in enumerate(items, 1):
                album_title = getattr(t, 'parentTitle', 'Unknown Album')
                artist_name = getattr(t, 'grandparentTitle', 'Unknown Artist')
                duration = (getattr(t, 'duration', 0) or 0) // 1000
                results.append(f"{i}. {t.title}  —  {artist_name} / {album_title}  ({duration//60}:{duration%60:02d})  [key: {t.ratingKey}]")

        elif album:
            filters = {"title": album}
            if genre:
                filters["genre"] = genre
            if artist:
                filters["artist.title"] = artist
            items = await asyncio.to_thread(lambda: section.searchAlbums(maxresults=limit, **filters))
            for i, a in enumerate(items, 1):
                artist_name = getattr(a, 'parentTitle', 'Unknown Artist')
                year = getattr(a, 'year', '')
                track_count = getattr(a, 'leafCount', '?')
                results.append(f"{i}. {a.title} ({year})  —  {artist_name}  ({track_count} tracks)  [key: {a.ratingKey}]")

        else:
            filters = {}
            if artist:
                filters["title"] = artist
            if genre:
                filters["genre"] = genre
            items = await asyncio.to_thread(lambda: section.searchArtists(maxresults=limit, **filters))
            for i, a in enumerate(items, 1):
                genres = ", ".join(g.tag for g in getattr(a, 'genres', [])[:3])
                album_count = getattr(a, 'childCount', '?')
                results.append(f"{i}. {a.title}  —  {genres or 'Unknown genre'}  ({album_count} albums)  [key: {a.ratingKey}]")

        if not results:
            return "No music found matching those filters."

        return "\n".join(results)
    except PlexMCPConnectionError:
        raise
    except Exception as e:
        logger.exception("Failed to search music")
        raise PlexMCPError("Failed to search music.") from e


@mcp.tool()
async def get_artist_details(artist_key: str) -> str:
    """
    Get details for a music artist including their albums.

    Parameters:
        artist_key: The rating key of the artist.

    Returns:
        Artist details and a list of albums.
    """
    try:
        plex = await get_plex_server()
        key = int(artist_key)
        artist = await asyncio.to_thread(plex.fetchItem, key)
        albums = await asyncio.to_thread(artist.albums)

        genres = ", ".join(g.tag for g in getattr(artist, 'genres', []))
        summary = getattr(artist, 'summary', 'No summary available.')

        lines = [
            f"Artist: {artist.title}",
            f"Genres: {genres or 'Unknown'}",
            f"Summary: {summary}",
            "",
            f"Albums ({len(albums)}):",
        ]
        for album in albums:
            year = getattr(album, 'year', '')
            track_count = getattr(album, 'leafCount', '?')
            lines.append(f"  {album.title} ({year})  —  {track_count} tracks  [key: {album.ratingKey}]")

        return "\n".join(lines)
    except PlexMCPConnectionError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Artist with key {artist_key} not found.")
    except Exception as e:
        logger.exception("Failed to fetch artist details for key '%s'", artist_key)
        raise PlexMCPError("Failed to fetch artist details.") from e


@mcp.tool()
async def get_album_details(album_key: str) -> str:
    """
    Get details for a music album including its track listing.

    Parameters:
        album_key: The rating key of the album.

    Returns:
        Album details and full track listing.
    """
    try:
        plex = await get_plex_server()
        key = int(album_key)
        album = await asyncio.to_thread(plex.fetchItem, key)
        tracks = await asyncio.to_thread(album.tracks)

        artist_name = getattr(album, 'parentTitle', 'Unknown Artist')
        year = getattr(album, 'year', '')
        genres = ", ".join(g.tag for g in getattr(album, 'genres', []))
        total_ms = sum(getattr(t, 'duration', 0) or 0 for t in tracks)
        total_mins = total_ms // 60_000

        lines = [
            f"Album: {album.title} ({year})",
            f"Artist: {artist_name}",
            f"Genres: {genres or 'Unknown'}",
            f"Tracks: {len(tracks)}  |  Runtime: {total_mins} minutes",
            "",
            "Track listing:",
        ]
        for track in tracks:
            duration_s = (getattr(track, 'duration', 0) or 0) // 1000
            track_num = getattr(track, 'trackNumber', '?')
            lines.append(f"  {track_num}. {track.title}  ({duration_s//60}:{duration_s%60:02d})  [key: {track.ratingKey}]")

        return "\n".join(lines)
    except PlexMCPConnectionError:
        raise
    except NotFound:
        raise PlexMCPNotFoundError(f"Album with key {album_key} not found.")
    except Exception as e:
        logger.exception("Failed to fetch album details for key '%s'", album_key)
        raise PlexMCPError("Failed to fetch album details.") from e


# --- Main Execution ---
if __name__ == "__main__":
    mcp.run(transport='stdio')
    

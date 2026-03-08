# Plex MCP Server

This is a Python-based MCP server that integrates with the Plex Media Server API to search and browse movies, TV shows, and music, manage playlists, and explore watch history. It uses the PlexAPI library for seamless interaction with your Plex server.

> Based on the original project by [@djbriane](https://github.com/djbriane/plex-mcp). Credit and thanks for the foundation this work builds on.

## Examples

Here are some examples of things you can ask Claude using this MCP server:

### Movies

**Search by director**
> "Show me all Christopher Nolan movies in my library"

**Search by rating and genre**
> "Find R-rated action movies over 2 hours long"

**Find something to watch**
> "Recommend me an unwatched drama from the 90s"

**Similar movies**
> "What movies are similar to Interstellar?"

**Recently added**
> "What movies were added to my library recently?"

**Most watched**
> "What are my most watched movies?"

---

### TV Shows

**Find something to watch**
> "Recommend a TV show from my library I haven't watched yet"

**Search by genre and year**
> "Find drama shows from 2020 or later"

**Check what's in progress**
> "What TV shows have I started watching?"

**Show details**
> "How many seasons of Breaking Bad do I have?"

---

### Music

**Search by genre**
> "Find all hip hop artists in my library"

**Browse an artist's discography**
> "Show me all albums by Radiohead"

**Browse a tracklist**
> "Show me the tracks on Abbey Road by The Beatles"

**Discover similar artists**
> "Show me artists in my library similar to Billy Strings"

---

### Playlists

**Create a movie playlist**
> "Create a playlist called 'Date Night' with the Christopher Nolan movies from my library"

**Create a music playlist**
> "Create a playlist about 2 hours long with music from the 80s"

**Browse playlists**
> "What playlists do I have?"

---

### Watch Activity

**History**
> "What did I watch recently?"

**On deck**
> "What do I have in progress?"

**Library stats**
> "How much content is in my Plex library?"

---

## Setup

### Prerequisites

- Python 3.13 or higher
- `uv` package manager
- A Plex Media Server with API access

### Installation

### Installing Manually
1. Clone this repository:
   ```
   git clone <repository-url>
   cd plex-mcp
   ```

2. Install dependencies with `uv`:
   ```
   uv venv
   source .venv/bin/activate
   uv sync
   ```

3. Configure environment variables for your Plex server:
   - `PLEX_TOKEN`: Your Plex authentication token
   - `PLEX_SERVER_URL`: Your Plex server URL (e.g., http://192.168.1.100:32400)

### Finding Your Plex Token

1. Sign in to [plex.tv](https://plex.tv) in your browser
2. Open Developer Tools (`F12` or `Cmd+Option+I` on Mac)
3. Go to the **Console** tab
4. Paste and run:
   ```javascript
   window.localStorage.getItem('myPlexAccessToken')
   ```
5. The token appears as output — it looks like `xxxxxxxxxxxxxxxxxxxx`

## Usage with Claude

Add the following configuration to your Claude app:

```json
{
    "mcpServers": {
        "plex": {
            "command": "uv",
            "args": [
                "--directory",
                "FULL_PATH_TO_PROJECT",
                "run",
                "src/plex_mcp/plex_mcp.py"
            ],
            "env": {
                "PLEX_TOKEN": "YOUR_PLEX_TOKEN",
                "PLEX_SERVER_URL": "YOUR_PLEX_SERVER_URL"
            }
        }
    }
}
```

## Available Commands

### Movies

| Command               | Description                                                                 |
|-----------------------|-----------------------------------------------------------------------------|
| `search_movies`       | Search by title, director, genre, actor, studio, year, rating, country, language, watched status, and duration. |
| `get_movie_details`   | Get detailed information about a specific movie by key.                    |
| `get_movie_genres`    | Get the genres for a specific movie.                                       |
| `recent_movies`       | Get recently added movies from your library.                               |
| `most_watched`        | Get the most watched movies or TV shows sorted by play count. Use `media_type="movies"` or `media_type="shows"`. |
| `get_similar_movies`  | Get Plex-recommended movies similar to a given movie.                      |

### TV Shows

| Command            | Description                                                                 |
|--------------------|-----------------------------------------------------------------------------|
| `search_tv_shows`  | Search for TV shows by title, genre, actor, studio, year, or watched status. |
| `get_show_details` | Get show info, genres, cast, and a full season/episode breakdown.          |

### Music

| Command              | Description                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| `search_music`       | Search for artists, albums, or tracks by name or genre.                    |
| `get_artist_details` | Get artist info and a full list of their albums.                           |
| `get_album_details`  | Get album info and full track listing with durations.                      |

### Playlists

| Command              | Description                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| `list_playlists`     | List all playlists on your Plex server.                                    |
| `get_playlist_items` | Get the items in a specific playlist.                                      |
| `create_playlist`    | Create a new playlist with specified movies.                               |
| `delete_playlist`    | Delete a playlist from your Plex server.                                   |
| `add_to_playlist`    | Add a movie to an existing playlist.                                       |

### Watch Activity

| Command              | Description                                                                 |
|----------------------|-----------------------------------------------------------------------------|
| `get_watch_history`  | Get recently played items across all libraries.                            |
| `get_on_deck`        | Get in-progress media with percentage completion.                          |
| `get_library_stats`  | Get item counts, total runtime, and storage size per library section.      |

## Operational Notes

- Result limits are capped to prevent accidental heavy queries (`limit`/`count` max is 50, `create_playlist` accepts up to 100 movie keys).
- `get_library_stats` scans up to 5,000 episodes/tracks per library section to calculate runtime and storage. Libraries exceeding this cap will show a `(capped at 5000)` note next to the count; item counts for top-level shows/artists are always exact.
- The Plex connection is cached and automatically re-established if it goes stale (e.g. after a server restart). Invalid tokens surface immediately without retrying.
- Tools raise `PlexMCPError`/`PlexMCPNotFoundError` for invalid inputs or missing items; MCP clients will surface these as tool errors rather than `"ERROR: ..."` strings.

## Running Tests

This project includes both unit tests and integration tests. Use the following instructions to run each type of test.

Test dependencies (`pytest`, `pytest-asyncio`) are in the `dev` dependency group. `uv sync` installs them automatically; if you're managing the environment manually, run:

```bash
uv sync --group dev
```

### Unit Tests

Unit tests use dummy data to verify the functionality of each module without requiring a live Plex server.

To run all unit tests:
```bash
uv run pytest
```

### Integration Tests

Integration tests run against a live Plex server using environment variables defined in a .env file. First, create a .env file in your project root with your Plex configuration:

```env
PLEX_SERVER_URL=https://your-plex-server-url:32400
PLEX_TOKEN=yourPlexTokenHere
```

Integration tests are marked with the integration marker. To run only the integration tests:

```bash
uv run pytest -m integration
```

If you are experiencing connection issues to your Plex server try running the integration tests to help troubleshoot.

## Code Style and Conventions

- **Module Structure:**
  Use clear section headers for imports, logging setup, utility functions, class definitions, global helpers, tool methods, and main execution (guarded by `if __name__ == "__main__":`).

- **Naming:**
  Use CamelCase for classes and lower_snake_case for functions, variables, and fixtures. In tests, list built-in fixtures (e.g. `monkeypatch`) before custom ones.

- **Constants:**
  Define configuration values and fixed parameters using `UPPER_CASE` (e.g. `MAX_LIMIT`, `DEFAULT_COUNT`). Declare constants near the top of the module after imports; do not modify them at runtime.

- **Type Hints:**
  Provide type hints for all function parameters and return values. Use built-in generics (`list[str]`, `dict[str, Any]`) and standard typing constructs (`Optional`, `Any`, etc.).

- **Documentation & Comments:**
  Include a concise docstring for every module, class, and function, with in-line comments for complex logic.

- **Error Handling & Logging:**
  Use Python’s `logging` module with parameterized messages (e.g. `logger.error("Failed: %s", err)`) rather than f-strings. Raise `PlexMCPError` (or a subclass) for tool errors rather than returning error strings.

- **Asynchronous Patterns:**
  Define I/O-bound functions as async and use `asyncio.to_thread()` to handle blocking operations.

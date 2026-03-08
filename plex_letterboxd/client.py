"""Plex API client utilities."""

from datetime import datetime
from typing import Any

from plexapi.exceptions import PlexApiException
from plexapi.server import PlexServer

from .config import PlexConfig
from .csv import ExportRow


def _parse_date_string(date_str: str) -> datetime:
    """Parse date string supporting both YYYY-MM-DD and YYYY-MM-DD-HH-MM formats."""
    for fmt in ("%Y-%m-%d-%H-%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {date_str}")


def _parse_date_filter(date_value: str | None) -> tuple[datetime | None, bool]:
    if date_value is None:
        return None, False
    return _parse_date_string(date_value), len(date_value) > 10


def extract_tmdb_id_from_plex_item(plex_item) -> str | None:
    """Extract TMDB ID from Plex item GUIDs (e.g., tmdb://<id>)."""
    for guid_obj in getattr(plex_item, "guids", []):
        guid_str = str(guid_obj.id)
        if guid_str.startswith("tmdb://"):
            return guid_str.split("//", 1)[1]
    return None


def connect_to_plex(plex_config: PlexConfig) -> PlexServer:
    """Connect to Plex server using provided configuration dict."""
    server = PlexServer(
        plex_config.url,
        plex_config.token,
        timeout=plex_config.timeout,
    )
    print(f"Connected to Plex server: {server.friendlyName}")
    return server


def get_users(server: PlexServer) -> list[dict[str, Any]]:
    """Return list of Plex users (owner + managed)."""
    users: list[dict[str, Any]] = []
    account = server.myPlexAccount()
    users.append(
        {
            "title": f"{account.title} (owner)",
            "username": account.username,
            "id": account.id,
            "legacy_id": 1,
        }
    )
    for user in account.users():
        users.append({"title": user.title, "username": user.username, "id": user.id})
    return users


def get_movies_library(server: PlexServer, library_name: str = "Movies"):
    """Get the Movies library from Plex by name."""
    library = server.library.section(library_name)
    print(f"Found library: {library.title} with {library.totalSize} items")
    return library


def _resolve_account_id(server: PlexServer, user_filter: str | None) -> int | None:
    if not user_filter:
        return None
    for user in get_users(server):
        if (
            user.get("username") == user_filter
            or user.get("title", "").lower() == str(user_filter).lower()
        ):
            return user.get("legacy_id", user.get("id"))
    return None


def get_watch_history(
    server: PlexServer,
    library,
    user_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[ExportRow]:
    """
    Get watch history for movies using fast server-side filtering,
    plus lazy metadata lookups.
    """
    watch_history: list[ExportRow] = []
    target_account_id = _resolve_account_id(server, user_filter)
    date_from_dt, from_has_time = _parse_date_filter(date_from)
    date_to_dt, _ = _parse_date_filter(date_to)

    print("Getting server watch history...")
    try:
        history = server.history(
            maxresults=5000,
            mindate=date_from_dt,
            accountID=target_account_id,
            librarySectionID=getattr(library, "key", None),
        )
    except TypeError:
        history = server.history()

    print(f"Found {len(history)} total history entries")

    movie_history = [
        entry for entry in history if getattr(entry, "type", None) == "movie"
    ]
    print(f"Found {len(movie_history)} movie watch entries")

    movie_cache: dict[str, dict[str, Any]] = {}
    processed_titles: set[str] = set()

    print("Processing movie history entries...")
    for entry in movie_history:
        if target_account_id is not None and entry.accountID != target_account_id:
            continue

        viewed_raw = getattr(entry, "viewedAt", None)
        if viewed_raw is None:
            continue
        viewed_at = (
            viewed_raw
            if isinstance(viewed_raw, datetime)
            else datetime.fromtimestamp(viewed_raw)
        )

        if date_from_dt is not None:
            if from_has_time:
                if viewed_at < date_from_dt:
                    continue
            elif viewed_at.date() < date_from_dt.date():
                continue
        if date_to_dt is not None and viewed_at.date() > date_to_dt.date():
            continue

        watch_date_str = viewed_at.strftime("%Y-%m-%d")
        movie_key = f"{entry.title}|{getattr(entry, 'year', 'Unknown')}"
        rating_key = str(entry.ratingKey)
        cached = movie_cache.get(rating_key)
        if cached is None:
            try:
                item = server.fetchItem(entry.ratingKey)
            except PlexApiException:
                cached = {}
            else:
                cached = {
                    "tmdb_id": extract_tmdb_id_from_plex_item(item),
                    "directors": (
                        ", ".join(d.tag for d in getattr(item, "directors", []))
                        if getattr(item, "directors", None)
                        else ""
                    ),
                    "genres": (
                        ", ".join(g.tag for g in getattr(item, "genres", []))
                        if getattr(item, "genres", None)
                        else ""
                    ),
                    "user_rating": getattr(item, "userRating", None),
                }
                movie_cache[rating_key] = cached

        directors = str(cached.get("directors", "") or "")
        genres = str(cached.get("genres", "") or "")
        if not directors and getattr(entry, "directors", None):
            directors = ", ".join(d.tag for d in entry.directors)
        if not genres and getattr(entry, "genres", None):
            genres = ", ".join(tag.tag for tag in entry.genres)

        watch_history.append(
            {
                "tmdbID": str(cached.get("tmdb_id", "") or ""),
                "Title": str(entry.title),
                "Year": str(getattr(entry, "year", "")),
                "Directors": directors,
                "WatchedDate": watch_date_str,
                "Rating": str(
                    cached.get("user_rating")
                    if cached.get("user_rating") is not None
                    else getattr(entry, "userRating", "")
                ),
                "Tags": genres,
                "Rewatch": "Yes" if movie_key in processed_titles else "No",
            }
        )
        processed_titles.add(movie_key)

    return watch_history

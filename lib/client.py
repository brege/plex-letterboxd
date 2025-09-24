"""
Plex API client utilities

This module encapsulates interactions with the Plex API used by the exporter:
- Connecting to the server
- Listing users and libraries
- Fetching watch history efficiently (server-side filtering when possible)
- Lazy metadata lookup for items (directors, genres, user rating, tmdb id)

Step 1 of refactor: Extract API-facing logic from exporter.py
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from plexapi.server import PlexServer
from plexapi.exceptions import PlexApiException


def extract_tmdb_id_from_plex_item(plex_item) -> Optional[str]:
    """Extract TMDB ID from Plex item GUIDs (e.g., tmdb://<id>)."""
    if hasattr(plex_item, "guids") and plex_item.guids:
        for guid_obj in plex_item.guids:
            guid_str = str(guid_obj.id)
            try:
                if guid_str.startswith("tmdb://"):
                    return guid_str.split("//")[1]
            except IndexError:
                continue
    return None


def connect_to_plex(plex_config: Dict[str, Any]) -> Optional[PlexServer]:
    """Connect to Plex server using provided configuration dict."""
    try:
        server = PlexServer(
            plex_config["url"],
            plex_config["token"],
            timeout=plex_config.get("timeout", 60),
        )
        print(f"Connected to Plex server: {server.friendlyName}")
        return server
    except PlexApiException as e:
        print(f"Error connecting to Plex: {e}")
        return None


def get_users(server: PlexServer) -> List[Dict[str, Any]]:
    """Return list of Plex users (owner + managed)."""
    try:
        users: List[Dict[str, Any]] = []
        account = server.myPlexAccount()
        users.append(
            {
                "title": f"{account.title} (owner)",
                "username": account.username,
                "id": account.id,
                "legacy_id": 1,  # most watch history is under legacy owner id
            }
        )
        for user in server.myPlexAccount().users():
            users.append({"title": user.title, "username": user.username, "id": user.id})
        return users
    except Exception as e:
        print(f"Error getting users: {e}")
        return []


def get_movies_library(server: PlexServer, library_name: str = "Movies"):
    """Get the Movies library from Plex by name."""
    try:
        library = server.library.section(library_name)
        print(f"Found library: {library.title} with {library.totalSize} items")
        return library
    except Exception as e:
        print(f"Error accessing library '{library_name}': {e}")
        return None


def _resolve_account_id(server: PlexServer, user_filter: Optional[str]) -> Optional[int]:
    if not user_filter:
        return None
    for user in get_users(server):
        if user.get("username") == user_filter or user.get("title", "").lower() == str(
            user_filter
        ).lower():
            return user.get("legacy_id", user.get("id"))
    return None


def get_watch_history(
    server: PlexServer,
    library,
    user_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get watch history for movies using fast server-side filtering and lazy metadata."""
    watch_history: List[Dict[str, Any]] = []

    try:
        target_account_id = _resolve_account_id(server, user_filter)

        print("Getting server watch history...")
        mindate_dt: Optional[datetime] = None
        if date_from:
            if isinstance(date_from, str):
                # Support YYYY-MM-DD-HH-MM and YYYY-MM-DD
                try:
                    mindate_dt = datetime.strptime(date_from, "%Y-%m-%d-%H-%M")
                except ValueError:
                    mindate_dt = datetime.strptime(date_from, "%Y-%m-%d")
            else:
                mindate_dt = (
                    datetime.combine(date_from, datetime.min.time())
                    if hasattr(date_from, "year") and not isinstance(date_from, datetime)
                    else date_from
                )

        try:
            history = server.history(
                maxresults=5000,
                mindate=mindate_dt,
                accountID=target_account_id,
                librarySectionID=getattr(library, "key", None),
            )
        except TypeError:
            history = server.history()

        print(f"Found {len(history)} total history entries")

        # Movies only
        movie_history = [h for h in history if getattr(h, "type", None) == "movie"]
        print(f"Found {len(movie_history)} movie watch entries")

        # Lazy metadata cache
        movie_cache: Dict[str, Dict[str, Any]] = {}

        print("Processing movie history entries...")
        processed_keys = set()

        for entry in movie_history:
            try:
                # User filter (server-side may not apply in older plexapi)
                if target_account_id is not None and entry.accountID != target_account_id:
                    continue

                # Viewed date
                if not getattr(entry, "viewedAt", None):
                    continue
                if isinstance(entry.viewedAt, datetime):
                    viewed_at = entry.viewedAt
                else:
                    viewed_at = datetime.fromtimestamp(entry.viewedAt)

                # Date filters
                if date_from:
                    if isinstance(date_from, str):
                        # If a timestamp was provided, filter at datetime precision
                        try:
                            df_dt = datetime.strptime(date_from, "%Y-%m-%d-%H-%M")
                            if viewed_at < df_dt:
                                continue
                        except ValueError:
                            df = datetime.strptime(date_from, "%Y-%m-%d").date()
                            if viewed_at.date() < df:
                                continue
                    else:
                        # date object
                        if viewed_at.date() < date_from:
                            continue
                if date_to:
                    dt = (
                        datetime.strptime(date_to, "%Y-%m-%d").date()
                        if isinstance(date_to, str)
                        else date_to
                    )
                    if viewed_at.date() > dt:
                        continue

                watch_date_str = viewed_at.strftime("%Y-%m-%d")

                # Unique key (title|year|date)
                watch_key = f"{entry.title}|{getattr(entry, 'year', 'Unknown')}|{watch_date_str}"

                # Metadata (lazy)
                cached = movie_cache.get(entry.ratingKey)
                if cached is None:
                    try:
                        item = server.fetchItem(entry.ratingKey)
                        cached = {
                            "tmdb_id": extract_tmdb_id_from_plex_item(item),
                            "directors": ", ".join(
                                [d.tag for d in getattr(item, "directors", [])]
                            )
                            if getattr(item, "directors", None)
                            else "",
                            "genres": ", ".join(
                                [g.tag for g in getattr(item, "genres", [])]
                            )
                            if getattr(item, "genres", None)
                            else "",
                            "user_rating": getattr(item, "userRating", None),
                        }
                        movie_cache[entry.ratingKey] = cached
                    except Exception:
                        cached = {}

                tmdb_id = cached.get("tmdb_id", "")
                directors = cached.get("directors", "")
                genres = cached.get("genres", "")

                # Fallbacks if cache miss
                if not directors and hasattr(entry, "directors") and entry.directors:
                    directors = ", ".join([d.tag for d in entry.directors])
                if not genres and hasattr(entry, "genres") and entry.genres:
                    genres = ", ".join([t.tag for t in entry.genres])

                # Build watch record
                record = {
                    "tmdbID": tmdb_id or "",
                    "Title": entry.title,
                    "Year": getattr(entry, "year", ""),
                    "Directors": directors,
                    "WatchedDate": watch_date_str,
                    "Rating": (
                        cached.get("user_rating")
                        if cached.get("user_rating") is not None
                        else (
                            getattr(entry, "userRating", "")
                            if hasattr(entry, "userRating")
                            else ""
                        )
                    ),
                    "Review": "",
                    "Tags": genres,
                    "Rewatch": (
                        "Yes"
                        if f"{entry.title}|{getattr(entry, 'year', 'Unknown')}" in {
                            k.split("|")[0] + "|" + k.split("|")[1] for k in processed_keys
                        }
                        else "No"
                    ),
                }

                watch_history.append(record)
                processed_keys.add(watch_key)
            except Exception as e:
                print(f"Error processing history entry: {e}")
                continue
    except Exception as e:
        print(f"Error getting watch history: {e}")

    return watch_history


def get_unwatched_movies(
    server: PlexServer, library, user_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return a list of unwatched movies for the given user (or overall)."""
    unwatched_movies: List[Dict[str, Any]] = []

    try:
        movies = library.all()
        print(f"Checking watch status for {len(movies)} movies...")

        target_account_id = _resolve_account_id(server, user_filter)

        for movie in movies:
            try:
                history = movie.history()
                user_watched = False
                if target_account_id is not None:
                    for watch in history:
                        if watch.accountID == target_account_id:
                            user_watched = True
                            break
                else:
                    user_watched = len(history) > 0

                if not user_watched:
                    tmdb_id = extract_tmdb_id_from_plex_item(movie)
                    unwatched_movies.append(
                        {
                            "tmdbID": tmdb_id or "",
                            "Title": movie.title,
                            "Year": movie.year,
                            "Directors": (
                                ", ".join([d.tag for d in movie.directors])
                                if movie.directors
                                else ""
                            ),
                            "Tags": (
                                ", ".join([t.tag for t in movie.genres])
                                if movie.genres
                                else ""
                            ),
                        }
                    )
            except Exception as e:
                print(f"Error checking movie '{movie.title}': {e}")
                continue
    except Exception as e:
        print(f"Error getting unwatched movies: {e}")

    return unwatched_movies

#!/usr/bin/env python3
"""
Plex to Letterboxd Export Script
Exports Plex watch history to Letterboxd-compatible CSV format
"""

import csv
import yaml
import argparse
from datetime import datetime
from plexapi.server import PlexServer
from plexapi.exceptions import PlexApiException


def extract_tmdb_id_from_plex_item(plex_item):
    """Extract TMDB ID from Plex item GUIDs"""
    if hasattr(plex_item, "guids") and plex_item.guids:
        for guid_obj in plex_item.guids:
            guid_str = str(guid_obj.id)
            try:
                if guid_str.startswith("tmdb://"):
                    return guid_str.split("//")[1]
            except IndexError:
                continue
    return None


def load_config(config_path="config.yaml"):
    """Load configuration from YAML file"""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def extract_plex_config(config):
    """Extract Plex configuration via local or Kometa config file"""

    # Check if using Kometa config method
    if "kometa" in config and config["kometa"].get("config_path"):
        kometa_config_path = config["kometa"]["config_path"]
        try:
            with open(kometa_config_path, "r") as f:
                kometa_config = yaml.safe_load(f)

            plex_config = kometa_config.get("plex", {})
            extracted_config = {
                "url": plex_config.get("url", "http://localhost:32400"),
                "token": plex_config.get("token"),
                "timeout": plex_config.get("timeout", 60),
            }
            print(f"Using Plex config from Kometa file: {kometa_config_path}")
        except Exception as e:
            print(f"Error reading Kometa config: {e}")
            return None

    # Check if using direct Plex config method
    elif "plex" in config and config["plex"].get("token"):
        extracted_config = {
            "url": config["plex"].get("url", "http://localhost:32400"),
            "token": config["plex"].get("token"),
            "timeout": config["plex"].get("timeout", 60),
        }
        print("Using direct Plex configuration from config file")

    else:
        print("Error: No valid Plex configuration found.")
        print(
            "Please configure either 'kometa.config_path' or "
            "'plex.token' in your config file."
        )
        return None

    # Apply URL override if specified
    plex_overrides = config.get("plex", {})
    if plex_overrides.get("url") and not config.get("plex", {}).get("token"):
        # Only override URL if we're not using direct plex config
        extracted_config["url"] = plex_overrides["url"]
        print(f"Overriding Plex URL: {extracted_config['url']}")

    return extracted_config


def connect_to_plex(plex_config):
    """Connect to Plex server using configuration"""
    try:
        server = PlexServer(
            plex_config["url"],
            plex_config["token"],
            timeout=plex_config["timeout"],
        )
        print(f"Connected to Plex server: {server.friendlyName}")
        return server
    except PlexApiException as e:
        print(f"Error connecting to Plex: {e}")
        return None


def get_users(server):
    """Get list of Plex users"""
    try:
        users = []
        # Get the server owner account
        account = server.myPlexAccount()
        users.append(
            {
                "title": f"{account.title} (owner)",
                "username": account.username,
                "id": account.id,
                # Most watch history is under account ID 1 (legacy owner)
                "legacy_id": 1,
            }
        )

        # Get managed users
        for user in server.myPlexAccount().users():
            users.append(
                {"title": user.title, "username": user.username, "id": user.id}
            )

        return users
    except Exception as e:
        print(f"Error getting users: {e}")
        return []


def get_movies_library(server, library_name="Movies"):
    """Get the Movies library from Plex"""
    try:
        library = server.library.section(library_name)
        print(f"Found library: {library.title} with {library.totalSize} items")
        return library
    except Exception as e:
        print(f"Error accessing library '{library_name}': {e}")
        return None


def get_watch_history(server, library, user_filter=None, date_from=None, date_to=None):
    """Get watch history for movies from Plex server history"""
    watch_history = []

    try:
        # Get server history instead of individual movie history
        print("Getting server watch history...")
        history = server.history()
        print(f"Found {len(history)} total history entries")

        # Filter for movies only
        movie_history = [
            entry
            for entry in history
            if hasattr(entry, "type") and entry.type == "movie"
        ]
        print(f"Found {len(movie_history)} movie watch entries")

        # Build cache of library movies with their TMDB IDs
        print("Building movie metadata cache...")
        movie_cache = {}
        try:
            all_movies = library.all()
            for movie in all_movies:
                movie_cache[movie.ratingKey] = {
                    "tmdb_id": extract_tmdb_id_from_plex_item(movie),
                    "directors": (
                        ", ".join([director.tag for director in movie.directors])
                        if movie.directors
                        else ""
                    ),
                    "genres": (
                        ", ".join([tag.tag for tag in movie.genres])
                        if movie.genres
                        else ""
                    ),
                }
        except Exception as e:
            print(f"Warning: Could not build movie cache: {e}")

        # Map user filter to account ID
        target_account_id = None
        if user_filter:
            # Try to find the user by name
            users = get_users(server)
            for user in users:
                if (
                    user["username"] == user_filter
                    or user["title"].lower() == user_filter.lower()
                ):
                    # Use legacy_id if available (for owner accounts with historical data)
                    target_account_id = user.get("legacy_id", user["id"])
                    break

        print("Processing movie history entries...")
        processed_titles = set()  # Track duplicates

        for entry in movie_history:
            try:
                # Filter by user if specified
                if (
                    target_account_id is not None
                    and entry.accountID != target_account_id
                ):
                    continue

                # Handle viewed date
                if hasattr(entry, "viewedAt") and entry.viewedAt:
                    if isinstance(entry.viewedAt, datetime):
                        viewed_at = entry.viewedAt
                    else:
                        viewed_at = datetime.fromtimestamp(entry.viewedAt)

                    # Filter by date if specified
                    if date_from:
                        # Handle both string and date object formats
                        if isinstance(date_from, str):
                            filter_date_from = datetime.strptime(
                                date_from, "%Y-%m-%d"
                            ).date()
                        else:
                            filter_date_from = date_from

                        if viewed_at.date() < filter_date_from:
                            continue

                    if date_to:
                        # Handle both string and date object formats
                        if isinstance(date_to, str):
                            filter_date_to = datetime.strptime(
                                date_to, "%Y-%m-%d"
                            ).date()
                        else:
                            filter_date_to = date_to

                        if viewed_at.date() > filter_date_to:
                            continue

                    watch_date_str = viewed_at.strftime("%Y-%m-%d")
                else:
                    continue  # Skip if no valid watch date

                # Create a unique key for this watch (to handle rewatches)
                watch_key = (
                    f"{entry.title}|{getattr(entry, 'year', 'Unknown')}|"
                    f"{watch_date_str}"
                )

                # Get metadata from cache using ratingKey
                cached_metadata = movie_cache.get(entry.ratingKey, {})
                tmdb_id = cached_metadata.get("tmdb_id", "")
                directors = cached_metadata.get("directors", "")
                genres = cached_metadata.get("genres", "")

                # Fallback to entry attributes if cache miss
                if not directors and hasattr(entry, "directors") and entry.directors:
                    directors = ", ".join(
                        [director.tag for director in entry.directors]
                    )
                if not genres and hasattr(entry, "genres") and entry.genres:
                    genres = ", ".join([tag.tag for tag in entry.genres])

                # Extract movie information
                watch_data = {
                    "tmdbID": tmdb_id or "",  # Add TMDB ID for better matching
                    "Title": entry.title,
                    "Year": getattr(entry, "year", ""),
                    "Directors": directors,
                    "WatchedDate": watch_date_str,
                    "Rating": (
                        getattr(entry, "userRating", "")
                        if hasattr(entry, "userRating")
                        else ""
                    ),
                    "Review": "",  # Plex doesn't have reviews in the same way
                    "Tags": genres,  # Will be processed later based on config
                    "Rewatch": (
                        "Yes"
                        if watch_key.split("|")[0] + "|" + watch_key.split("|")[1]
                        in [
                            k.split("|")[0] + "|" + k.split("|")[1]
                            for k in processed_titles
                        ]
                        else "No"
                    ),
                }

                watch_history.append(watch_data)
                processed_titles.add(watch_key)

            except Exception as e:
                print(f"Error processing history entry: {e}")
                continue

    except Exception as e:
        print(f"Error getting watch history: {e}")

    return watch_history


def process_watch_history_by_config(watch_history, config):
    """Process watch history based on letterboxd config options"""
    letterboxd_config = config.get("letterboxd", {})

    # Handle rewatch mode filtering
    rewatch_mode = letterboxd_config.get("rewatch_mode", "all")
    if rewatch_mode in [False, None, "false", "null"]:
        # Remove all rewatches, keep only first watches
        seen_movies = set()
        filtered_history = []
        for entry in sorted(watch_history, key=lambda x: x["WatchedDate"]):
            movie_key = (entry["Title"].lower(), entry["Year"])
            if movie_key not in seen_movies:
                entry["Rewatch"] = "No"
                filtered_history.append(entry)
                seen_movies.add(movie_key)
        watch_history = filtered_history
    elif rewatch_mode == "first":
        # Keep only first watch of each movie
        seen_movies = set()
        filtered_history = []
        for entry in sorted(watch_history, key=lambda x: x["WatchedDate"]):
            movie_key = (entry["Title"].lower(), entry["Year"])
            if movie_key not in seen_movies:
                entry["Rewatch"] = "No"
                filtered_history.append(entry)
                seen_movies.add(movie_key)
        watch_history = filtered_history
    elif rewatch_mode == "last":
        # Keep only most recent watch of each movie
        movie_latest = {}
        for entry in watch_history:
            movie_key = (entry["Title"].lower(), entry["Year"])
            if (
                movie_key not in movie_latest
                or entry["WatchedDate"] > movie_latest[movie_key]["WatchedDate"]
            ):
                movie_latest[movie_key] = entry
        watch_history = list(movie_latest.values())
        for entry in watch_history:
            entry["Rewatch"] = "No"
    # "all" mode keeps everything as-is with rewatch marking

    # Handle rewatch marking
    mark_rewatches = letterboxd_config.get("mark_rewatches", True)
    if not mark_rewatches:
        for entry in watch_history:
            entry["Rewatch"] = "No"

    # Handle tags
    export_genres = letterboxd_config.get("export_genres_as_tags", False)
    custom_tags = letterboxd_config.get("custom_tags", None)

    for entry in watch_history:
        tags = []

        # Add genres if enabled
        if export_genres and entry.get("Tags"):
            tags.append(entry["Tags"])

        # Add custom tags
        if custom_tags:
            tags.append(custom_tags)

        # Update tags field
        entry["Tags"] = ", ".join(tags) if tags else ""

    return watch_history


def export_to_csv(
    watch_history,
    output_file,
    include_rating=False,
    include_reviews=False,
    max_films=1900,
):
    """Export watch history to Letterboxd-compatible CSV"""

    # Define columns based on configuration - tmdbID first for better matching
    columns = ["tmdbID", "Title", "Year", "Directors", "WatchedDate"]

    if include_rating:
        columns.append("Rating")
    if include_reviews:
        columns.append("Review")

    columns.extend(["Tags", "Rewatch"])

    # Limit number of films if necessary
    if len(watch_history) > max_films:
        print(
            f"Warning: {len(watch_history)} films found, limiting to "
            f"{max_films} for Letterboxd compatibility"
        )
        watch_history = watch_history[:max_films]

    # Write to CSV
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()

        for watch in watch_history:
            # Only include configured columns
            filtered_watch = {col: watch.get(col, "") for col in columns}
            writer.writerow(filtered_watch)

    print(f"Exported {len(watch_history)} watch records to {output_file}")


def get_unwatched_movies(server, library, user_filter=None):
    """Get list of movies that haven't been watched by specified user"""
    unwatched_movies = []

    try:
        movies = library.all()
        print(f"Checking watch status for {len(movies)} movies...")

        for movie in movies:
            try:
                history = movie.history()

                # Check if user has watched this movie
                user_watched = False
                if user_filter:
                    for watch in history:
                        if watch.accountID == user_filter:
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
                                ", ".join(
                                    [director.tag for director in movie.directors]
                                )
                                if movie.directors
                                else ""
                            ),
                            "Tags": (
                                ", ".join([tag.tag for tag in movie.genres])
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


def generate_default_filename(user_filter=None, date_from=None, date_to=None):
    """Generate smart default filename based on user and date"""
    from datetime import datetime

    user_part = user_filter if user_filter else "all"

    if date_from and date_to:
        date_part = f"{date_from}-to-{date_to}"
    elif date_from:
        date_part = f"from-{date_from}"
    elif date_to:
        date_part = f"to-{date_to}"
    else:
        date_part = datetime.now().strftime("%Y-%m-%d")

    return f"plex-watched-{user_part}-{date_part}.csv"


def load_cached_data(file_path):
    """Load existing CSV data for slicing"""
    import csv
    from datetime import datetime

    cached_data = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                watch_date = datetime.strptime(row["WatchedDate"], "%Y-%m-%d")
                cached_data.append(
                    {
                        "tmdbID": row.get("tmdbID", ""),
                        "Title": row["Title"],
                        "Year": row["Year"],
                        "Directors": row["Directors"],
                        "WatchedDate": row["WatchedDate"],
                        "Rating": row.get("Rating", ""),
                        "Review": row.get("Review", ""),
                        "Tags": row.get("Tags", ""),
                        "Rewatch": row.get("Rewatch", ""),
                        "date_obj": watch_date,
                    }
                )
            except ValueError:
                continue
    return cached_data


def slice_cached_data(cached_data, date_from=None, date_to=None):
    """Slice cached data by date range"""
    if not date_from and not date_to:
        return cached_data

    sliced_data = []
    for entry in cached_data:
        entry_date = entry["date_obj"].date()

        if date_from:
            if isinstance(date_from, str):
                filter_date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            else:
                filter_date_from = date_from
            if entry_date < filter_date_from:
                continue

        if date_to:
            if isinstance(date_to, str):
                filter_date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            else:
                filter_date_to = date_to
            if entry_date > filter_date_to:
                continue

        # Remove the date_obj helper field
        clean_entry = {k: v for k, v in entry.items() if k != "date_obj"}
        sliced_data.append(clean_entry)

    return sliced_data


def main():
    parser = argparse.ArgumentParser(
        description="Export Plex watch history to Letterboxd CSV"
    )
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument(
        "--output", help="Output CSV file (overrides config and default)"
    )
    parser.add_argument("--user", help="Filter by specific user (overrides config)")
    parser.add_argument(
        "--from-date", help="Export from date YYYY-MM-DD (overrides config)"
    )
    parser.add_argument(
        "--to-date", help="Export to date YYYY-MM-DD (overrides config)"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Show unwatched vs watched movie comparison",
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use cached CSV data instead of querying Plex API",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Handle cached data mode
    if args.cached:
        user_filter = (
            args.user if args.user is not None else config["export"].get("user")
        )
        date_from = (
            args.from_date
            if args.from_date is not None
            else config["export"].get("date_from")
        )
        date_to = args.to_date

        # Find existing full dataset CSV
        import glob

        user_part = user_filter if user_filter else "all"
        pattern = f"plex-watched-{user_part}-*.csv"
        csv_files = glob.glob(pattern)

        if not csv_files:
            print(f"Error: No cached CSV files found matching pattern: {pattern}")
            print("Run without --cached to generate initial dataset")
            return

        # Use the most recent full dataset
        csv_file = max(csv_files, key=lambda f: f.split("-")[-1])
        print(f"Using cached data from: {csv_file}")

        # Load and slice cached data
        cached_data = load_cached_data(csv_file)
        watch_history = slice_cached_data(cached_data, date_from, date_to)

        print(f"Loaded {len(cached_data)} total entries")
        print(f"Filtered to {len(watch_history)} entries for date range")

        if date_from:
            print(f"  - From date: {date_from}")
        if date_to:
            print(f"  - To date: {date_to}")

        # Process cached data with config options
        if watch_history:
            watch_history = process_watch_history_by_config(watch_history, config)
    else:
        # Extract Plex configuration (supports Kometa or direct config)
        plex_config = extract_plex_config(config)

        if not plex_config or not plex_config.get("token"):
            print("Error: No valid Plex configuration found")
            return

        # Connect to Plex
        server = connect_to_plex(plex_config)
        if not server:
            return

        # Get users
        users = get_users(server)
        print("\nAvailable users:")
        for user in users:
            print(f"  - {user['title']} ({user['username']})")

        # Get Movies library
        library = get_movies_library(
            server, config["export"].get("library_name", "Movies")
        )
        if not library:
            return

        # Get watch history - command line overrides config
        user_filter = (
            args.user if args.user is not None else config["export"].get("user")
        )
        date_from = (
            args.from_date
            if args.from_date is not None
            else config["export"].get("date_from")
        )
        date_to = args.to_date

        print("\nExporting watch history...")
        if user_filter:
            print(f"  - Filtered by user: {user_filter}")
        if date_from:
            print(f"  - From date: {date_from}")
        if date_to:
            print(f"  - To date: {date_to}")

        watch_history = get_watch_history(
            server, library, user_filter, date_from, date_to
        )

    # Process watch history based on config options
    if watch_history:
        watch_history = process_watch_history_by_config(watch_history, config)

    if not watch_history:
        print("No watch history found matching criteria")
        if not args.compare:
            return

    # Show comparison if requested
    if args.compare:
        print(f"\n--- COMPARISON FOR USER: {user_filter or 'ALL'} ---")

        # Get watched movie titles
        watched_titles = set()
        for watch in watch_history:
            watched_titles.add(f"{watch['Title']} ({watch['Year']})")

        # Get unwatched movies
        unwatched_movies = get_unwatched_movies(server, library, user_filter)
        unwatched_titles = set()
        for movie in unwatched_movies:
            unwatched_titles.add(f"{movie['Title']} ({movie['Year']})")

        print(f"\nWatched movies: {len(watched_titles)}")
        print(f"Unwatched movies: {len(unwatched_titles)}")

        # Show some examples
        if watched_titles:
            print("\nFirst 10 watched movies:")
            for i, title in enumerate(sorted(watched_titles)):
                if i >= 10:
                    break
                print(f"  - {title}")

        if unwatched_titles:
            print("\nFirst 10 unwatched movies:")
            for i, title in enumerate(sorted(unwatched_titles)):
                if i >= 10:
                    break
                print(f"  - {title}")

        # Set operations
        all_movies = watched_titles | unwatched_titles
        print(f"\nTotal unique movies in library: {len(all_movies)}")

        if not args.output:
            return  # Don't export if just comparing

    if not watch_history:
        return

    # Determine output filename with smart defaults
    if args.output:
        output_file = args.output
    elif config["export"].get("output_file"):
        output_file = config["export"]["output_file"]
    else:
        output_file = generate_default_filename(user_filter, date_from, date_to)
    export_to_csv(
        watch_history,
        output_file,
        include_rating=config["letterboxd"]["include_rating"],
        include_reviews=config["letterboxd"]["include_reviews"],
        max_films=config["letterboxd"]["max_films_per_file"],
    )

    print(f"\nExport complete! Import the file '{output_file}' to Letterboxd.")


if __name__ == "__main__":
    main()

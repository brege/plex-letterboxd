#!/usr/bin/env python3
"""
Plex to Letterboxd Export Script
Exports Plex watch history to Letterboxd-compatible CSV format
"""

import argparse
from datetime import datetime
from lib.client import (
    connect_to_plex,
    get_users,
    get_movies_library,
    get_watch_history,
    get_unwatched_movies,
)
from lib.csv import (
    transform_history,
    write_csv,
)
from lib.config import load_config, extract_plex_config, normalize_config

# Config helpers are provided by lib.config

# Moved: process_watch_history_by_config, export_to_csv (see lib/csv.py)

def generate_default_filename(user_filter=None, date_from=None, date_to=None):
    """Generate smart default filename based on user and date"""
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
    parser.add_argument(
        "--list-users",
        action="store_true",
        help="List available Plex users before export",
    )

    args = parser.parse_args()

    # Load and normalize configuration
    config = load_config(args.config)
    config = normalize_config(config)

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
            watch_history = transform_history(watch_history, config)
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

        # Get users (only list when no user filter provided, unless --list-users is set)
        users = get_users(server)
        user_filter = (
            args.user if args.user is not None else config["export"].get("user")
        )
        if args.list_users or not user_filter:
            print("\nAvailable users:")
            for user in users:
                print(f"  - {user['title']} ({user['username']})")
            # If explicitly listing users, exit before exporting
            if args.list_users:
                return

        # Get Movies library
        library = get_movies_library(
            server, config["export"].get("library", "Movies")
        )
        if not library:
            return

        # Get watch history - command line overrides config
        # user_filter already derived above
        date_from = (
            args.from_date if args.from_date is not None else config["export"].get("from")
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
        watch_history = transform_history(watch_history, config)

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
    elif config["export"].get("output"):
        output_file = config["export"]["output"]
    else:
        output_file = generate_default_filename(user_filter, date_from, date_to)
    write_csv(
        watch_history,
        output_file,
        include_rating=config["csv"]["rating"],
        max_films=config["csv"]["max_rows"],
    )

    print(f"\nExport complete! Import the file '{output_file}' to Letterboxd.")


if __name__ == "__main__":
    main()

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

def _timestamp_format_str(cfg_fmt: str) -> str:
    return "%Y-%m-%d-%H-%M" if cfg_fmt == "datetime" else "%Y-%m-%d"


def _now_stamp(cfg_fmt: str) -> str:
    return datetime.now().strftime(_timestamp_format_str(cfg_fmt))


def build_output_path(config, user_filter: str | None, export_dir_override: str | None) -> str:
    """Build output path using export.dir and file_pattern with {user} and {timestamp}."""
    import os

    user_part = user_filter if user_filter else "all"
    export_dir = export_dir_override or config["export"].get("dir", "data")
    pattern = config["export"].get("file_pattern", "plex-watched-{user}-{timestamp}.csv")
    ts = _now_stamp(config["export"].get("timestamp_format", "datetime"))
    filename = pattern.format(user=user_part, timestamp=ts)
    os.makedirs(export_dir, exist_ok=True)
    return os.path.join(export_dir, filename)


def _parse_stamp_or_date(s: str, cfg_fmt: str | None = None):
    from datetime import datetime as _dt
    # Try configured format first
    if cfg_fmt:
        try:
            return _dt.strptime(s, _timestamp_format_str(cfg_fmt))
        except ValueError:
            pass
    # Then try both known formats
    for fmt in ("%Y-%m-%d-%H-%M", "%Y-%m-%d"):
        try:
            return _dt.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError("Unrecognized timestamp/date format")


def find_checkpoint_from_csv(config, user_filter: str | None, export_dir_override: str | None):
    """Find latest CSV for user in export.dir and return a from-date string (YYYY-MM-DD-HH-MM)."""
    import os
    import glob

    export_dir = export_dir_override or config["export"].get("dir", "data")
    user_part = user_filter if user_filter else "all"

    # Match both new timestamped and legacy date-only filenames
    patterns = [
        os.path.join(export_dir, f"plex-watched-{user_part}-*.csv"),
    ]

    candidates = []
    for pat in patterns:
        for path in glob.glob(pat):
            base = os.path.basename(path)
            stem = base[:-4] if base.endswith('.csv') else base
            # Extract the trailing token after last '-'
            token = stem.split(f"plex-watched-{user_part}-", 1)[-1]
            try:
                dt = _parse_stamp_or_date(token, config["export"].get("timestamp_format", "datetime"))
                candidates.append((dt, path))
            except ValueError:
                continue

    if not candidates:
        return None

    latest_dt, latest_path = max(candidates, key=lambda t: t[0])
    # Return formatted stamp for mindate
    return latest_dt.strftime("%Y-%m-%d-%H-%M")


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
    parser.add_argument(
        "--export-dir",
        help="Override export directory (defaults to config export.dir)",
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
        # If no from-date, infer from last CSV checkpoint when enabled
        if not date_from and config.get("checkpoint", {}).get("use_csv", True):
            date_from = find_checkpoint_from_csv(config, user_filter, args.export_dir)
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
        output_file = build_output_path(config, user_filter, args.export_dir)
    write_csv(
        watch_history,
        output_file,
        include_rating=config["csv"]["rating"],
        max_films=config["csv"]["max_rows"],
    )

    print(f"\nExport complete! Import the file '{output_file}' to Letterboxd.")


if __name__ == "__main__":
    main()

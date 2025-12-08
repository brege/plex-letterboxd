#!/usr/bin/env python3
"""
Plex to Letterboxd Export Script
Exports Plex watch history to Letterboxd-compatible CSV format
"""

import os
from datetime import datetime

import click

from .client import (
    connect_to_plex,
    get_movies_library,
    get_users,
    get_watch_history,
)
from .config import extract_plex_config, load_config
from .csv import (
    transform_history,
    write_csv,
)


def _override_or_config(arg_value, config_value):
    """Return CLI arg if provided, otherwise config value"""
    return arg_value if arg_value is not None else config_value


# Moved: process_watch_history_by_config, export_to_csv (see lib/csv.py)


def _timestamp_format_str(cfg_fmt: str) -> str:
    return "%Y-%m-%d-%H-%M" if cfg_fmt == "datetime" else "%Y-%m-%d"


def _now_stamp(cfg_fmt: str) -> str:
    return datetime.now().strftime(_timestamp_format_str(cfg_fmt))


def build_output_path(
    config, user_filter: str | None, export_dir_override: str | None
) -> str:
    """
    Build output path using export.dir and file_pattern with
    {user} and {timestamp} placeholders.
    """
    import os

    user_part = user_filter if user_filter else "all"
    export_dir = export_dir_override or config["export"].get("dir", "data")
    pattern = config["export"].get(
        "file_pattern", "plex-watched-{user}-{timestamp}.csv"
    )
    ts = _now_stamp(config["export"].get("timestamp_format", "datetime"))
    filename = pattern.format(user=user_part, timestamp=ts)
    os.makedirs(export_dir, exist_ok=True)
    return os.path.join(export_dir, filename)


def _symlink(output_file, config):
    """Create symlink to CSV if configured"""
    symlink_location = config["export"].get("symlink_location")
    if not symlink_location:
        return

    try:
        expanded_location = os.path.expanduser(symlink_location)
        if not os.path.isdir(expanded_location):
            return

        symlink_path = os.path.join(expanded_location, os.path.basename(output_file))
        try:
            os.remove(symlink_path)
        except FileNotFoundError:
            pass

        os.symlink(os.path.abspath(output_file), symlink_path)
        print(f"Created symlink: {symlink_path}")
    except Exception:
        pass


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


def find_checkpoint_from_csv(
    config, user_filter: str | None, export_dir_override: str | None
):
    """
    Find latest CSV for the user in export.dir and return an after-date
    string (YYYY-MM-DD-HH-MM).
    """
    import glob
    import os

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
            stem = base[:-4] if base.endswith(".csv") else base
            # Extract the trailing token after last '-'
            token = stem.split(f"plex-watched-{user_part}-", 1)[-1]
            try:
                dt = _parse_stamp_or_date(
                    token, config["export"].get("timestamp_format", "datetime")
                )
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
    with open(file_path, encoding="utf-8") as f:
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


@click.command()
@click.option(
    "--config",
    type=click.Path(),
    default=lambda: (
        (xdg := os.path.join(click.get_app_dir("plex-letterboxd"), "config.yaml")),
        xdg if os.path.exists(xdg) else "config.yaml",
    )[1],
    help="Config file path (default: XDG config dir or ./config.yaml)",
)
@click.option("--output", help="Output CSV file (overrides config and default)")
@click.option("--user", help="Filter by specific user (overrides config)")
@click.option(
    "--after", help="Export movies watched after date YYYY-MM-DD (overrides config)"
)
@click.option(
    "--before", help="Export movies watched before date YYYY-MM-DD (overrides config)"
)
@click.option(
    "--cached", is_flag=True, help="Use cached CSV data instead of querying Plex API"
)
@click.option(
    "--list-users", is_flag=True, help="List available Plex users before export"
)
@click.option(
    "--export-dir", help="Override export directory (defaults to config export.dir)"
)
def main(config, output, user, after, before, cached, list_users, export_dir):
    # Load configuration (confuse handles normalization)
    config_data = load_config(config)

    # Handle cached data mode
    if cached:
        user_filter = _override_or_config(user, config_data["export"].get("user"))
        date_from = _override_or_config(after, config_data["export"].get("after"))
        date_to = _override_or_config(before, config_data["export"].get("before"))

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
            watch_history = transform_history(watch_history, config_data)
    else:
        # Extract Plex configuration (supports Kometa or direct config)
        plex_config = extract_plex_config(config_data)

        if not plex_config or not plex_config.get("token"):
            print("Error: No valid Plex configuration found")
            return

        # Connect to Plex
        server = connect_to_plex(plex_config)
        if not server:
            return

        # Get users (only list when no user filter provided, unless --list-users is set)
        users = get_users(server)
        user_filter = _override_or_config(user, config_data["export"].get("user"))
        if list_users or not user_filter:
            print("\nAvailable users:")
            for user in users:
                print(f"  - {user['title']} ({user['username']})")
            # If explicitly listing users, exit before exporting
            if list_users:
                return

        # Get Movies library
        library = get_movies_library(
            server, config_data["export"].get("library", "Movies")
        )
        if not library:
            return

        # Get watch history - command line overrides config
        # user_filter already derived above
        date_from = _override_or_config(after, config_data["export"].get("after"))
        # If no from-date, infer from last CSV checkpoint when enabled
        if not date_from and config_data.get("checkpoint", {}).get("use_csv", True):
            date_from = find_checkpoint_from_csv(config_data, user_filter, export_dir)
        date_to = _override_or_config(before, config_data["export"].get("before"))

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
        watch_history = transform_history(watch_history, config_data)

    if not watch_history:
        print("No watch history found matching criteria")
        return

    # Determine output filename with smart defaults
    if output:
        output_file = output
    elif config_data["export"].get("output"):
        output_file = config_data["export"]["output"]
    else:
        output_file = build_output_path(config_data, user_filter, export_dir)
    write_csv(
        watch_history,
        output_file,
        include_rating=config_data["csv"]["rating"],
        max_films=config_data["csv"]["max_rows"],
    )

    _symlink(output_file, config_data)

    print(f"\nExport complete! Import the file '{output_file}' to Letterboxd.")


if __name__ == "__main__":
    main()

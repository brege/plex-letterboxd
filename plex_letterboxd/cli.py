#!/usr/bin/env python3
"""Plex to Letterboxd export CLI."""

import os
from datetime import datetime
from pathlib import Path
from typing import TypedDict

import click
import yaml
from plexapi.exceptions import PlexApiException
from pydantic import ValidationError

from .client import (
    connect_to_plex,
    get_movies_library,
    get_users,
    get_watch_history,
)
from .config import AppConfig, ExportConfig, extract_plex_config, load_config
from .csv import (
    ExportRow,
    transform_history,
    write_csv,
)


class CachedRow(TypedDict):
    tmdbID: str
    Title: str
    Year: str
    Directors: str
    WatchedDate: str
    Rating: str
    Tags: str
    Rewatch: str
    date_obj: datetime


def _override_or_config(arg_value, config_value):
    """Return CLI arg if provided, otherwise config value"""
    return arg_value if arg_value is not None else config_value


# Moved: process_watch_history_by_config, export_to_csv (see lib/csv.py)


def _timestamp_format_str(cfg_fmt: str) -> str:
    return "%Y-%m-%d-%H-%M" if cfg_fmt == "datetime" else "%Y-%m-%d"


def _now_stamp(cfg_fmt: str) -> str:
    return datetime.now().strftime(_timestamp_format_str(cfg_fmt))


def build_output_path(
    config: AppConfig,
    user_filter: str | None,
    export_dir_override: str | None,
) -> Path:
    """Build output path using export.dir and file_pattern."""
    user_part = user_filter if user_filter else "all"
    export_dir = (
        Path(export_dir_override).expanduser()
        if export_dir_override
        else config.export.dir
    )
    filename = config.export.file_pattern.format(
        user=user_part,
        timestamp=_now_stamp(config.export.timestamp_format),
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / filename


def _symlink(output_file: Path, export_config: ExportConfig) -> None:
    """Create symlink to CSV if configured."""
    symlink_location = export_config.symlink_location
    if not symlink_location:
        return

    if not symlink_location.is_dir():
        raise click.ClickException(
            f"Symlink location is not a directory: {symlink_location}"
        )

    symlink_path = symlink_location / output_file.name
    try:
        symlink_path.unlink()
    except FileNotFoundError:
        pass

    symlink_path.symlink_to(output_file.resolve())
    print(f"Created symlink: {symlink_path}")


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
    config: AppConfig,
    user_filter: str | None,
    export_dir_override: str | None,
) -> str | None:
    """Return the latest CSV checkpoint timestamp for the selected user."""
    export_dir = (
        Path(export_dir_override).expanduser()
        if export_dir_override
        else config.export.dir
    )
    user_part = user_filter if user_filter else "all"

    candidates: list[tuple[datetime, Path]] = []
    for path in export_dir.glob(f"plex-watched-{user_part}-*.csv"):
        stem = path.stem
        token = stem.split(f"plex-watched-{user_part}-", 1)[-1]
        try:
            dt = _parse_stamp_or_date(token, config.export.timestamp_format)
        except ValueError:
            continue
        candidates.append((dt, path))

    if not candidates:
        return None

    latest_dt, _latest_path = max(candidates, key=lambda item: item[0])
    return latest_dt.strftime("%Y-%m-%d-%H-%M")


def load_cached_data(file_path: Path) -> list[CachedRow]:
    """Load existing CSV data for slicing."""
    import csv

    cached_data: list[CachedRow] = []
    with file_path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            watch_date_raw = row.get("WatchedDate")
            if not watch_date_raw:
                raise ValueError(f"Missing WatchedDate in cached CSV {file_path}")
            watch_date = datetime.strptime(watch_date_raw, "%Y-%m-%d")
            cached_data.append(
                {
                    "tmdbID": row.get("tmdbID", ""),
                    "Title": row.get("Title", ""),
                    "Year": row.get("Year", ""),
                    "Directors": row.get("Directors", ""),
                    "WatchedDate": watch_date_raw,
                    "Rating": row.get("Rating", ""),
                    "Tags": row.get("Tags", ""),
                    "Rewatch": row.get("Rewatch", ""),
                    "date_obj": watch_date,
                }
            )
    return cached_data


def _strip_cached_date(entry: CachedRow) -> ExportRow:
    return {
        "tmdbID": entry["tmdbID"],
        "Title": entry["Title"],
        "Year": entry["Year"],
        "Directors": entry["Directors"],
        "WatchedDate": entry["WatchedDate"],
        "Rating": entry["Rating"],
        "Tags": entry["Tags"],
        "Rewatch": entry["Rewatch"],
    }


def slice_cached_data(
    cached_data: list[CachedRow],
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[ExportRow]:
    """Slice cached data by date range."""
    if not date_from and not date_to:
        return [_strip_cached_date(entry) for entry in cached_data]

    filter_date_from = _parse_stamp_or_date(date_from).date() if date_from else None
    filter_date_to = _parse_stamp_or_date(date_to).date() if date_to else None
    sliced_data: list[ExportRow] = []
    for entry in cached_data:
        entry_date = entry["date_obj"].date()

        if filter_date_from is not None and entry_date < filter_date_from:
            continue
        if filter_date_to is not None and entry_date > filter_date_to:
            continue

        sliced_data.append(_strip_cached_date(entry))

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
    try:
        config_data = load_config(config)
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"Configuration file not found at {Path(config).expanduser()}"
        ) from exc
    except yaml.YAMLError as exc:
        raise click.ClickException(
            f"Error parsing configuration file {config}: {exc}"
        ) from exc
    except ValidationError as exc:
        raise click.ClickException(str(exc)) from exc

    user_filter = _override_or_config(user, config_data.export.user)
    date_from = _override_or_config(after, config_data.export.after)
    date_to = _override_or_config(before, config_data.export.before)

    if cached:
        user_part = user_filter if user_filter else "all"
        export_dir_path = (
            Path(export_dir).expanduser() if export_dir else config_data.export.dir
        )
        csv_files = list(export_dir_path.glob(f"plex-watched-{user_part}-*.csv"))

        if not csv_files:
            raise click.ClickException(
                f"No cached CSV files found in {export_dir_path} for user {user_part}"
            )

        csv_file = max(
            csv_files,
            key=lambda path: _parse_stamp_or_date(
                path.stem.split(f"plex-watched-{user_part}-", 1)[-1],
                config_data.export.timestamp_format,
            ),
        )
        print(f"Using cached data from: {csv_file}")

        cached_data = load_cached_data(csv_file)
        watch_history = slice_cached_data(cached_data, date_from, date_to)

        print(f"Loaded {len(cached_data)} total entries")
        print(f"Filtered to {len(watch_history)} entries for date range")

        if date_from:
            print(f"  - From date: {date_from}")
        if date_to:
            print(f"  - To date: {date_to}")

    else:
        try:
            plex_config = extract_plex_config(config_data)
            server = connect_to_plex(plex_config)

            users = get_users(server)
            if list_users or not user_filter:
                print("\nAvailable users:")
                for account in users:
                    print(f"  - {account['title']} ({account['username']})")
                if list_users:
                    return

            library = get_movies_library(server, config_data.export.library)

            if not date_from and config_data.checkpoint.use_csv:
                date_from = find_checkpoint_from_csv(
                    config_data,
                    user_filter,
                    export_dir,
                )

            print("\nExporting watch history...")
            if user_filter:
                print(f"  - Filtered by user: {user_filter}")
            if date_from:
                print(f"  - From date: {date_from}")
            if date_to:
                print(f"  - To date: {date_to}")

            watch_history = get_watch_history(
                server,
                library,
                user_filter,
                date_from,
                date_to,
            )
        except (
            FileNotFoundError,
            ValidationError,
            ValueError,
            PlexApiException,
        ) as exc:
            raise click.ClickException(str(exc)) from exc
        except yaml.YAMLError as exc:
            raise click.ClickException(f"Error parsing Kometa config: {exc}") from exc

    if watch_history:
        watch_history = transform_history(watch_history, config_data.csv)

    if not watch_history:
        print("No watch history found matching criteria")
        return

    if output:
        output_file = Path(output).expanduser()
    elif config_data.export.output:
        output_file = config_data.export.output
    else:
        output_file = build_output_path(config_data, user_filter, export_dir)

    write_csv(
        watch_history,
        output_file,
        include_rating=config_data.csv.rating,
        max_films=config_data.csv.max_rows,
    )

    _symlink(output_file, config_data.export)

    print(f"\nExport complete! Import the file '{output_file}' to Letterboxd.")


if __name__ == "__main__":
    main()

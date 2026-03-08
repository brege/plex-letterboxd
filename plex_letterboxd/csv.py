"""
Letterboxd CSV utilities

Responsible for:
- Transforming raw watch history with config (rewatch handling, tags, rating conversion)
- Writing Letterboxd-compatible CSV files
"""

import csv
from pathlib import Path
from typing import TypedDict

from .config import CsvConfig


class ExportRow(TypedDict):
    tmdbID: str
    Title: str
    Year: str
    Directors: str
    WatchedDate: str
    Rating: str
    Tags: str
    Rewatch: str


def transform_history(
    watch_history: list[ExportRow],
    config: CsvConfig,
) -> list[ExportRow]:
    """Process watch history based on CSV config options."""

    rewatch_mode = config.rewatch
    if rewatch_mode in {"false", "null", "first"}:
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

    if not config.mark_rewatch:
        for entry in watch_history:
            entry["Rewatch"] = "No"

    for entry in watch_history:
        tags = []

        if config.genres and entry.get("Tags"):
            tags.append(entry["Tags"])

        if config.tags:
            tags.append(config.tags)

        entry["Tags"] = ", ".join(tags) if tags else ""

    if config.rating:
        for entry in watch_history:
            r = entry.get("Rating")
            try:
                if r in (None, ""):
                    entry["Rating"] = ""
                    continue
                r_float = float(r)
                if r_float <= 0:
                    entry["Rating"] = ""
                    continue
                if r_float <= 5.0:
                    letterboxd_rating = round(r_float / 0.5) * 0.5
                else:
                    letterboxd_rating = round(r_float) / 2.0
                letterboxd_rating = max(0.5, min(5.0, letterboxd_rating))
                entry["Rating"] = f"{letterboxd_rating:.1f}".rstrip("0").rstrip(".")
            except (ValueError, TypeError):
                entry["Rating"] = ""

    return watch_history


def write_csv(
    watch_history: list[ExportRow],
    output_file: str | Path,
    include_rating: bool = False,
    max_films: int = 1900,
) -> None:
    """Export watch history to Letterboxd-compatible CSV."""

    columns = ["tmdbID", "Title", "Year", "Directors", "WatchedDate"]

    if include_rating:
        columns.append("Rating")

    columns.extend(["Tags", "Rewatch"])

    if len(watch_history) > max_films:
        print(
            f"Warning: {len(watch_history)} films found, limiting to "
            f"{max_films} for Letterboxd compatibility"
        )
        watch_history = watch_history[:max_films]

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        for watch in watch_history:
            filtered_watch = {col: watch.get(col, "") for col in columns}
            writer.writerow(filtered_watch)

    print(f"Exported {len(watch_history)} watch records to {output_file}")

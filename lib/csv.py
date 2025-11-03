"""
Letterboxd CSV utilities

Responsible for:
- Transforming raw watch history with config (rewatch handling, tags, rating conversion)
- Writing Letterboxd-compatible CSV files
"""

import csv


def transform_history(watch_history, config):
    """Process watch history based on CSV config options"""
    letterboxd_config = config.get("csv", {})

    # Handle rewatch mode filtering
    rewatch_mode = letterboxd_config.get("rewatch", "all")
    if rewatch_mode in [False, None, "false", "null", "first"]:
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
    mark_rewatches = letterboxd_config.get("mark_rewatch", True)
    if not mark_rewatches:
        for entry in watch_history:
            entry["Rewatch"] = "No"

    # Handle tags
    export_genres = letterboxd_config.get("genres", False)
    custom_tags = letterboxd_config.get("tags")

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

    # Handle rating conversion (Plex 1–10 -> Letterboxd 0.5–5.0)
    include_rating = bool(letterboxd_config.get("rating", False))
    if include_rating:
        for entry in watch_history:
            r = entry.get("Rating")
            try:
                # Treat empty/None/zero as unrated
                if r in (None, ""):
                    entry["Rating"] = ""
                    continue
                r_float = float(r)
                if r_float <= 0:
                    entry["Rating"] = ""
                    continue
                # If value looks like already-converted (<= 5), normalize to half-star
                if r_float <= 5.0:
                    letterboxd_rating = round(r_float / 0.5) * 0.5
                else:
                    # Plex user ratings are typically 1–10; map to 0.5–5.0
                    letterboxd_rating = round(r_float) / 2.0
                # Clamp to Letterboxd bounds
                letterboxd_rating = max(0.5, min(5.0, letterboxd_rating))
                entry["Rating"] = f"{letterboxd_rating:.1f}".rstrip("0").rstrip(".")
            except (ValueError, TypeError):
                entry["Rating"] = ""

    return watch_history


def write_csv(
    watch_history,
    output_file,
    include_rating=False,
    max_films=1900,
):
    """Export watch history to Letterboxd-compatible CSV"""

    # Define columns based on configuration - tmdbID first for better matching
    columns = ["tmdbID", "Title", "Year", "Directors", "WatchedDate"]

    if include_rating:
        columns.append("Rating")
    # Review column removed (Plex has no per-user text reviews)

    columns.extend(["Tags", "Rewatch"])

    # Limit number of films if necessary
    if len(watch_history) > max_films:
        print(
            (
                f"Warning: {len(watch_history)} films found, limiting to "
                f"{max_films} for Letterboxd compatibility"
            )
        )
        watch_history = watch_history[:max_films]

    # Write to CSV
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        for watch in watch_history:
            filtered_watch = {col: watch.get(col, "") for col in columns}
            writer.writerow(filtered_watch)

    print(f"Exported {len(watch_history)} watch records to {output_file}")

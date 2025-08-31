#!/usr/bin/env python3
"""
Plex vs Letterboxd Data Analysis
Analyzes overlap between Plex export and existing Letterboxd data
"""

import csv
import argparse
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from collections import defaultdict


def load_plex_data(file_path):
    """Load Plex watch history from CSV"""
    plex_data = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                watch_date = datetime.strptime(row["WatchedDate"], "%Y-%m-%d")
                plex_data.append(
                    {
                        "title": row["Title"],
                        "year": row["Year"],
                        "date": watch_date,
                        "tmdb_id": row.get("tmdbID", ""),
                        "source": "Plex",
                    }
                )
            except ValueError:
                continue  # Skip invalid dates
    return plex_data


def load_letterboxd_data(file_path):
    """Load Letterboxd watch history from CSV"""
    letterboxd_data = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                watch_date = datetime.strptime(row["Date"], "%Y-%m-%d")
                letterboxd_data.append(
                    {
                        "title": row["Name"],
                        "year": row["Year"],
                        "date": watch_date,
                        "uri": row.get("Letterboxd URI", ""),
                        "source": "Letterboxd",
                    }
                )
            except ValueError:
                continue  # Skip invalid dates
    return letterboxd_data


def filter_data_by_date(data, before_date=None, after_date=None):
    """Filter data entries by date range"""
    filtered_data = []

    for entry in data:
        entry_date = entry["date"]

        # Check before date filter
        if before_date and entry_date >= before_date:
            continue

        # Check after date filter
        if after_date and entry_date < after_date:
            continue

        filtered_data.append(entry)

    return filtered_data


def create_timeline_plot(
    plex_data,
    letterboxd_data,
    output_file=None,
    before_date=None,
    after_date=None,
):
    """Create timeline plot showing data overlap"""
    # Apply date filters
    plex_data = filter_data_by_date(plex_data, before_date, after_date)
    letterboxd_data = filter_data_by_date(letterboxd_data, before_date, after_date)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    # Extract dates
    plex_dates = [entry["date"] for entry in plex_data]
    letterboxd_dates = [entry["date"] for entry in letterboxd_data]
    if not plex_dates and not letterboxd_dates:
        print("No valid dates found in either dataset")
        return

    all_dates = plex_dates + letterboxd_dates
    if not all_dates:
        print("No dates to plot")
        return

    min_date = min(all_dates)
    max_date = max(all_dates)

    # Create monthly bins
    current_date = min_date.replace(day=1)
    months = []
    while current_date <= max_date:
        months.append(current_date)
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)

    # Count watches per month
    plex_monthly = defaultdict(int)
    letterboxd_monthly = defaultdict(int)
    for entry in plex_data:
        month_key = entry["date"].replace(day=1)
        plex_monthly[month_key] += 1
    for entry in letterboxd_data:
        month_key = entry["date"].replace(day=1)
        letterboxd_monthly[month_key] += 1

    plex_counts = [plex_monthly[month] for month in months]
    letterboxd_counts = [letterboxd_monthly[month] for month in months]

    # Plot 1: Side-by-Side Comparison (former ax2)
    width = timedelta(days=15)
    ax1.bar(
        [d - width / 2 for d in months],
        plex_counts,
        width=width,
        alpha=0.7,
        label="Plex",
        color="orange",
    )
    ax1.bar(
        [d + width / 2 for d in months],
        letterboxd_counts,
        width=width,
        alpha=0.7,
        label="Letterboxd",
        color="green",
    )
    ax1.set_title("Side-by-Side Comparison")
    ax1.set_ylabel("Movies Watched")
    ax1.legend()
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, len(months) // 12)))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

    # Plot 2: Cumulative (former ax3)
    plex_cumulative = []
    letterboxd_cumulative = []
    plex_sum = 0
    letterboxd_sum = 0
    for i, month in enumerate(months):
        plex_sum += plex_counts[i]
        letterboxd_sum += letterboxd_counts[i]
        plex_cumulative.append(plex_sum)
        letterboxd_cumulative.append(letterboxd_sum)

    ax2.plot(
        months,
        plex_cumulative,
        label="Plex (Cumulative)",
        color="orange",
        linewidth=2,
    )
    ax2.plot(
        months,
        letterboxd_cumulative,
        label="Letterboxd (Cumulative)",
        color="green",
        linewidth=2,
    )
    ax2.set_title("Cumulative Watch Count")
    ax2.set_ylabel("Total Movies Watched")
    ax2.set_xlabel("Date")
    ax2.legend()
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, len(months) // 12)))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

    plt.tight_layout()
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches="tight")
        print(f"Plot saved to: {output_file}")
    else:
        plt.show()


def analyze_overlap(plex_data, letterboxd_data, before_date=None, after_date=None):
    """Analyze overlap between datasets"""
    # Apply date filters
    original_plex_count = len(plex_data)
    original_letterboxd_count = len(letterboxd_data)

    plex_data = filter_data_by_date(plex_data, before_date, after_date)
    letterboxd_data = filter_data_by_date(letterboxd_data, before_date, after_date)

    print("\n=== DATA ANALYSIS ===")

    # Show filtering info if applied
    if before_date or after_date:
        print("Date filters applied:")
        if after_date:
            print(f"  After: {after_date.strftime('%Y-%m-%d')}")
        if before_date:
            print(f"  Before: {before_date.strftime('%Y-%m-%d')}")
        print(f"  Plex entries: {original_plex_count} -> {len(plex_data)}")
        print(
            f"  Letterboxd entries: {original_letterboxd_count} -> "
            f"{len(letterboxd_data)}"
        )
        print()

    # Basic stats
    print(f"Plex entries: {len(plex_data)}")
    print(f"Letterboxd entries: {len(letterboxd_data)}")

    if not plex_data and not letterboxd_data:
        print("No data to analyze")
        return

    # Date ranges
    if plex_data:
        plex_dates = [entry["date"] for entry in plex_data]
        plex_start = min(plex_dates)
        plex_end = max(plex_dates)
        print(
            f"Plex date range: {plex_start.strftime('%Y-%m-%d')} to "
            f"{plex_end.strftime('%Y-%m-%d')}"
        )

    if letterboxd_data:
        letterboxd_dates = [entry["date"] for entry in letterboxd_data]
        letterboxd_start = min(letterboxd_dates)
        letterboxd_end = max(letterboxd_dates)
        print(
            f"Letterboxd date range: {letterboxd_start.strftime('%Y-%m-%d')}"
            f" to {letterboxd_end.strftime('%Y-%m-%d')}"
        )

    # Overlap analysis by title+year
    plex_movies = set()
    letterboxd_movies = set()

    for entry in plex_data:
        movie_key = (entry["title"].lower(), entry["year"])
        plex_movies.add(movie_key)

    for entry in letterboxd_data:
        movie_key = (entry["title"].lower(), entry["year"])
        letterboxd_movies.add(movie_key)

    overlapping_movies = plex_movies.intersection(letterboxd_movies)
    plex_only = plex_movies - letterboxd_movies
    letterboxd_only = letterboxd_movies - plex_movies

    print("\n=== MOVIE OVERLAP ===")
    print(f"Movies in both: {len(overlapping_movies)}")
    print(f"Plex only: {len(plex_only)}")
    print(f"Letterboxd only: {len(letterboxd_only)}")

    if overlapping_movies:
        print("\nFirst 10 overlapping movies:")
        for i, (title, year) in enumerate(sorted(overlapping_movies)):
            if i >= 10:
                break
            print(f"  - {title.title()} ({year})")

    # Time-based overlap
    if plex_data and letterboxd_data:
        all_dates = [entry["date"] for entry in plex_data + letterboxd_data]
        min_date = min(all_dates)
        max_date = max(all_dates)
        date_range = (max_date - min_date).days

        print("\n=== TIME ANALYSIS ===")
        print(f"Total date span: {date_range} days " f"({date_range/365.25:.1f} years)")

        if plex_data and letterboxd_data:
            # Find overlapping time period
            overlap_start = max(min(plex_dates), min(letterboxd_dates))
            overlap_end = min(max(plex_dates), max(letterboxd_dates))

            if overlap_start <= overlap_end:
                overlap_days = (overlap_end - overlap_start).days
                print(
                    f"Overlapping period: "
                    f"{overlap_start.strftime('%Y-%m-%d')} to "
                    f"{overlap_end.strftime('%Y-%m-%d')} ({overlap_days} days)"
                )
            else:
                print("No overlapping time period")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Plex vs Letterboxd data overlap"
    )
    parser.add_argument("--plex", required=True, help="Plex export CSV file")
    parser.add_argument(
        "--letterboxd", required=True, help="Letterboxd export CSV file"
    )
    parser.add_argument("--output", help="Save plot to file (optional)")
    parser.add_argument("--no-plot", action="store_true", help="Skip generating plot")
    parser.add_argument(
        "--to-date", help="Only include data before this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--from-date", help="Only include data after this date (YYYY-MM-DD)"
    )

    args = parser.parse_args()

    try:
        # Parse date filters
        before_date = None
        after_date = None

        if args.to_date:
            try:
                before_date = datetime.strptime(args.to_date, "%Y-%m-%d")
            except ValueError:
                print(f"Error: Invalid to-date format: {args.to_date}")
                return

        if args.from_date:
            try:
                after_date = datetime.strptime(args.from_date, "%Y-%m-%d")
            except ValueError:
                print(f"Error: Invalid from-date format: {args.from_date}")
                return

        # Load data
        print(f"Loading Plex data from: {args.plex}")
        plex_data = load_plex_data(args.plex)

        print(f"Loading Letterboxd data from: {args.letterboxd}")
        letterboxd_data = load_letterboxd_data(args.letterboxd)

        # Analyze
        analyze_overlap(plex_data, letterboxd_data, before_date, after_date)

        # Show command to generate Plex data for this date range
        if before_date or after_date:
            print("\nTo export Plex data for this date range:")
            cmd_parts = ["python3 exporter.py"]
            if after_date:
                cmd_parts.append(f"--from-date {after_date.strftime('%Y-%m-%d')}")
            if before_date:
                cmd_parts.append(f"--to-date {before_date.strftime('%Y-%m-%d')}")
            cmd_parts.append("--user YOUR_USERNAME")
            cmd_parts.append("# OR --cached")
            print(" ".join(cmd_parts))

        # Plot
        if not args.no_plot:
            print("\n=== GENERATING PLOT ===")
            create_timeline_plot(
                plex_data,
                letterboxd_data,
                args.output,
                before_date,
                after_date,
            )

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()

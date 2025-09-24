## Plex to Letterboxd Exporter

Export your Plex watch history to a Letterboxd‑compatible CSV with TMDB IDs for reliable matching.

### Install
```bash
git clone https://github.com/brege/plex-letterboxd.git
cd plex-letterboxd
pip install plexapi pyyaml
```

### Configure
Use either a direct Plex token or your existing Kometa config.

Direct token
```yaml
plex:
  url: http://your-plex-server:32400
  token: YOUR_PLEX_TOKEN
  timeout: 60
```

Kometa config
```yaml
kometa:
  config_path: ./path/to/kometa/config.yml
```

Exporter options live in `config.yaml` (see `config.example.yaml`).
- export: output, from, to, user, library
- csv: rating, review, max_rows, genres, tags, rewatch, mark_rewatch

Timestamped filenames use `{timestamp}` in the pattern and default to minute precision. You can set `export.timestamp_format: date` to anchor re‑imports at the start of each day (intentionally re‑exporting the boundary day).

Ratings (optional): set `csv.rating: true`. Ratings convert from Plex 1–10 to Letterboxd 0.5–5.0.

### Run
- List users
```bash
python3 exporter.py --list-users
```

- Export for a user
```bash
python3 exporter.py --user USERNAME --output plex-export.csv
```

- Export a date range
```bash
python3 exporter.py --user USERNAME --from-date 2024-01-01 --to-date 2024-12-31 --output plex-export-2024.csv
```

Import at https://letterboxd.com/import/

More options: `python3 exporter.py --help`

Notes: read‑only to Plex (does not modify server data).

### Output CSV Columns

| Field         | Description                          |
|:------------- |:------------------------------------- |
| `tmdbID`      | TMDB ID for precise matching          |
| `Title`       | Movie title                           |
| `Year`        | Release year                          |
| `Directors`   | Director names                        |
| `WatchedDate` | When you watched it (YYYY‑MM‑DD)      |
| `Rating`      | Your rating (0.5–5.0), if enabled     |
| `Tags`        | Genres and/or custom tags, if enabled |
| `Rewatch`     | Whether it's a rewatch                |

**Configuration**: see [`config.example.yaml`](config.example.yaml)

<!-- Comparison tool usage moved out of README to keep essentials only. See compare.py --help if needed. -->

---

### Ratings

- Enable ratings with `csv.rating: true` in `config.yaml`.
- Plex user ratings (1–10) are converted to Letterboxd’s 0.5–5.0 scale (half‑star rounding).
- Unrated or 0 values export as blank.

Example:
```yaml
csv:
  rating: true
```

Notes: This tool is read‑only to Plex.

---

[MIT License](LICENSE)

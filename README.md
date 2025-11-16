## Plex to Letterboxd Exporter

Exports Plex watch history and ratings to a Letterboxd‑compatible CSV file using TMDB IDs for reliable matching.

### Install

From [PyPI](https://pypi.org/project/plex-letterboxd/):

```bash
pip install plex-letterboxd
```

From source:

```bash
git clone https://github.com/brege/plex-letterboxd.git
cd plex-letterboxd
pip install .
```

### Configure

There are two ways to include your Plex token.

**Option 1:** Set your Plex token in `config.yaml`:
```yaml
plex:
  url: http://your-plex-server:32400
  token: PLEX_TOKEN
  timeout: 60
```

**Option 2:** Kometa users may source Kometa's config in this project's `config.yaml`:
```yaml
kometa:
  config_path: ./path/to/Kometa/config.yml
```

Exporter options are in `config.yaml`.
- export: output, after, before, user, library
- csv: rating, review, max\_rows, genres, tags, rewatch, mark\_rewatch

See [`config.example.yaml`](config.example.yaml) for available options.

### Usage

- List users
```bash
plex-letterboxd --list-users
```

- Export for a specific user
```bash
plex-letterboxd --user USERNAME --output plex-export.csv
```

- Export a date range
```bash
plex-letterboxd \
    --user USERNAME \
    --after 2024-01-01 \
    --before 2024-12-31 \
    --output plex-export-2024.csv
```

Import at https://letterboxd.com/import/

See `plex-letterboxd --help` for CLI options.

### Output CSV Columns

| Field         | Description                           |
|:------------- |:------------------------------------- |
| `tmdbID`      | TMDB ID for precise matching          |
| `Title`       | Movie title                           |
| `Year`        | Release year                          |
| `Directors`   | Director names                        |
| `WatchedDate` | When you watched it (YYYY‑MM‑DD)      |
| `Rating`      | Your rating (0.5–5.0), if enabled     |
| `Tags`        | Genres and/or custom tags, if enabled |
| `Rewatch`     | Whether it's a rewatch                |

---

## Automated Exports

Set up a [systemd timer](https://www.freedesktop.org/software/systemd/man/systemd.timer.html) for automated monthly exports with CSV checkpointing.

### Setup Timer

Monthly
```bash
bash <(curl -s https://raw.githubusercontent.com/brege/plex-letterboxd/refs/heads/main/systemd/install.sh)
```

Or weekly
```bash
bash <(curl -s https://raw.githubusercontent.com/brege/plex-letterboxd/refs/heads/main/systemd/install.sh) weekly
```

The timer will run the exporter on your chosen schedule, producing CSV files in `~/.config/plex-letterboxd/data/`. Configure the output data directory via `config.yaml` to change.

I suggest running this on the same machine Plex runs on, since it's typically always online.

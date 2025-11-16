## Plex to Letterboxd Exporter

Exports Plex watch history and ratings to a Letterboxd‑compatible CSV file using TMDB IDs for reliable matching.

### Install

```bash
git clone https://github.com/brege/plex-letterboxd.git
cd plex-letterboxd
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Debian/Ubuntu: if `python3 -m venv` is missing, install it:
```bash
sudo apt install python3-venv
```

The remaining commands assume you're activated in the virtual environment `source .venv/bin/activate`.

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
python exporter.py --list-users
```

- Export for a specific user
```bash
python exporter.py --user USERNAME --output plex-export.csv
```

- Export a date range
```bash
python exporter.py \
    --user USERNAME \
    --after 2024-01-01 \
    --before 2024-12-31 \
    --output plex-export-2024.csv
```

Import at https://letterboxd.com/import/

See `python exporter.py --help` for CLI options.

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

Set up a [systemd timer](https://www.freedesktop.org/software/systemd/man/systemd.timer.html) for automated monthly exports with CSV checkpointing:

### Install Timer

Edit the cadence to your liking. The included timer runs monthly.

```bash
sudo cp systemd/plex-letterboxd.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable plex-letterboxd.timer
sudo systemctl start plex-letterboxd.timer
```

This timer will run the exporter once a month, producing a new, monthly CSV file in the configured `data/` directory.  You can run this on your Plex machine or other machine since the exporter only queries the Plex API.

---

[MIT License](LICENSE)

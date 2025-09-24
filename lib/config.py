"""
Config utilities

- Load YAML config
- Merge/resolve Kometa or direct Plex config
- Normalize option keys to a concise, consistent schema (no legacy keys)

Canonical schema (after normalization):

export:
  output: str|None
  from: str|None           # YYYY-MM-DD
  to: str|None             # YYYY-MM-DD
  user: str|None
  library: str             # default: Movies
  dir: str                 # default: data
  file_pattern: str        # default: plex-watched-{user}-{timestamp}.csv
  timestamp_format: str    # 'datetime' (YYYY-MM-DD-HH-MM) or 'date' (YYYY-MM-DD)

csv:
  rating: bool
  max_rows: int
  genres: bool             # export genres as tags
  tags: str|None
  rewatch: str             # all|first|last|false
  mark_rewatch: bool
"""

from __future__ import annotations

from typing import Any, Dict
import yaml


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def extract_plex_config(config: Dict[str, Any]) -> Dict[str, Any] | None:
    # Prefer Kometa token if configured
    if "kometa" in config and config["kometa"].get("config_path"):
        kometa_config_path = config["kometa"]["config_path"]
        try:
            with open(kometa_config_path, "r", encoding="utf-8") as f:
                kometa = yaml.safe_load(f) or {}
            plex_cfg = kometa.get("plex", {})
            extracted = {
                "url": plex_cfg.get("url", "http://localhost:32400"),
                "token": plex_cfg.get("token"),
                "timeout": plex_cfg.get("timeout", 60),
            }
            print(f"Using Plex config from Kometa file: {kometa_config_path}")
        except Exception as e:
            print(f"Error reading Kometa config: {e}")
            return None
    elif "plex" in config and config["plex"].get("token"):
        extracted = {
            "url": config["plex"].get("url", "http://localhost:32400"),
            "token": config["plex"].get("token"),
            "timeout": config["plex"].get("timeout", 60),
        }
        print("Using direct Plex configuration from config file")
    else:
        print("Error: No valid Plex configuration found.")
        print(
            (
                "Please configure either 'kometa.config_path' or 'plex.token' "
                "in your config file."
            )
        )
        return None

    # Allow URL override at top-level plex.url
    plex_overrides = config.get("plex", {})
    if plex_overrides.get("url") and not config.get("plex", {}).get("token"):
        extracted["url"] = plex_overrides["url"]
        print(f"Overriding Plex URL: {extracted['url']}")

    return extracted


def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(config)  # shallow copy is fine

    # Normalize export block
    export_in = dict(config.get("export", {}) or {})
    out_export = {
        "output": export_in.get("output"),
        "from": export_in.get("from"),
        "to": export_in.get("to"),
        "user": export_in.get("user"),
        "library": export_in.get("library", "Movies"),
        "dir": export_in.get("dir", "data"),
        "file_pattern": export_in.get(
            "file_pattern", "plex-watched-{user}-{timestamp}.csv"
        ),
        "timestamp_format": export_in.get("timestamp_format", "datetime"),
    }
    out["export"] = out_export

    # Normalize CSV/Letterboxd block
    lb_in = dict(config.get("csv", {}) or {})
    out_csv = {
        "rating": lb_in.get("rating", False),
        "max_rows": lb_in.get("max_rows", 1900),
        "genres": lb_in.get("genres", False),
        "tags": lb_in.get("tags"),
        "rewatch": lb_in.get("rewatch", "all"),
        "mark_rewatch": lb_in.get("mark_rewatch", True),
    }
    out["csv"] = out_csv

    # Checkpoint settings
    cp_in = dict(config.get("checkpoint", {}) or {})
    out_cp = {
        "use_csv": cp_in.get("use_csv", True),
        "path": cp_in.get("path", ".last-run.json"),
    }
    out["checkpoint"] = out_cp

    # Clamp timestamp_format
    tf = out["export"].get("timestamp_format", "datetime")
    if tf not in ("datetime", "date"):
        out["export"]["timestamp_format"] = "datetime"

    return out

"""
Config utilities

- Load YAML config
- Merge/resolve Kometa or direct Plex config
- Normalize option keys to a concise, consistent schema (no legacy keys)

Canonical schema (after normalization):

export:
  output: str|None
  after: str|None          # YYYY-MM-DD
  before: str|None         # YYYY-MM-DD
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
import os
import click
import yaml


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    # Get the XDG config root
    config_root = click.get_app_dir("plex-letterboxd")

    # Load raw YAML first
    with open(path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}

    # Apply defaults
    defaults = {
        "export": {
            "output": None,
            "after": None,
            "before": None,
            "user": None,
            "library": "Movies",
            "dir": os.path.join(config_root, "data"),
            "file_pattern": "plex-watched-{user}-{timestamp}.csv",
            "timestamp_format": "datetime",
        },
        "csv": {
            "rating": False,
            "max_rows": 1900,
            "genres": False,
            "tags": None,
            "rewatch": "all",
            "mark_rewatch": True,
        },
        "checkpoint": {
            "use_csv": True,
            "path": ".last-run.json",
        },
    }

    # Deep merge defaults with user config
    result = {}
    for section, section_defaults in defaults.items():
        result[section] = {**section_defaults, **raw_config.get(section, {})}

    # Add non-default sections as-is (plex, kometa)
    for key in raw_config:
        if key not in defaults:
            result[key] = raw_config[key]

    # Resolve relative paths in export.dir relative to config root
    if "export" in result:
        dir_path = result["export"]["dir"]
        if not os.path.isabs(dir_path):
            result["export"]["dir"] = os.path.join(config_root, dir_path)

    return result


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

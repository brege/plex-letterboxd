"""Configuration models and Plex config extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import click
import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TimestampFormat = Literal["datetime", "date"]
RewatchMode = Literal["all", "first", "last", "false", "null"]


def _default_export_dir() -> Path:
    return Path(click.get_app_dir("plex-letterboxd")) / "data"


def _resolve_path(raw: str | Path | None, base_path: Path) -> Path | None:
    if raw is None:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (base_path / candidate).resolve()
    return candidate


def _resolve_required_path(raw: str | Path, base_path: Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (base_path / candidate).resolve()
    return candidate


class PlexConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: NonEmptyStr = "http://localhost:32400"
    token: NonEmptyStr
    timeout: int = Field(default=60, ge=1)


class PlexOverrides(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: NonEmptyStr | None = None
    token: NonEmptyStr | None = None
    timeout: int = Field(default=60, ge=1)


class KometaConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    config_path: Path


class ExportConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    output: Path | None = None
    after: str | None = None
    before: str | None = None
    user: str | None = None
    library: NonEmptyStr = "Movies"
    dir: Path = Field(default_factory=_default_export_dir)
    file_pattern: NonEmptyStr = "plex-watched-{user}-{timestamp}.csv"
    timestamp_format: TimestampFormat = "datetime"
    symlink_location: Path | None = None


class CsvConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rating: bool = False
    max_rows: int = Field(default=1900, ge=1)
    genres: bool = False
    tags: str | None = None
    rewatch: RewatchMode = "all"
    mark_rewatch: bool = True


class CheckpointConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    use_csv: bool = True
    path: Path = Path(".last-run.json")


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plex: PlexOverrides = Field(default_factory=PlexOverrides)
    kometa: KometaConfig | None = None
    export: ExportConfig = Field(default_factory=ExportConfig)
    csv: CsvConfig = Field(default_factory=CsvConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)

    @model_validator(mode="after")
    def validate_plex_source(self) -> AppConfig:
        if self.kometa is None and self.plex.token is None:
            raise ValueError(
                "configure either kometa.config_path or plex.token in the config file"
            )
        return self


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path).expanduser()
    with config_path.open(encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}
    config = AppConfig.model_validate(raw_config)
    base_path = config_path.parent.resolve()
    if config.kometa is not None:
        config.kometa.config_path = _resolve_required_path(
            config.kometa.config_path,
            base_path,
        )
    config.export.dir = _resolve_required_path(config.export.dir, base_path)
    config.export.output = _resolve_path(config.export.output, base_path)
    config.export.symlink_location = _resolve_path(
        config.export.symlink_location,
        base_path,
    )
    config.checkpoint.path = _resolve_required_path(
        config.checkpoint.path,
        base_path,
    )
    return config


def extract_plex_config(config: AppConfig) -> PlexConfig:
    if config.kometa is not None:
        with config.kometa.config_path.open(encoding="utf-8") as handle:
            kometa_raw = yaml.safe_load(handle) or {}
        if not isinstance(kometa_raw, dict):
            raise ValueError(
                "Unexpected YAML structure in Kometa config "
                f"{config.kometa.config_path}"
            )
        plex_raw = kometa_raw.get("plex")
        if not isinstance(plex_raw, dict):
            raise ValueError(
                f"Kometa config '{config.kometa.config_path}' is missing "
                "a 'plex' section"
            )
        plex_config = PlexConfig.model_validate(plex_raw)
        if config.plex.url is not None and config.plex.token is None:
            plex_config.url = config.plex.url
        return plex_config

    return PlexConfig.model_validate(config.plex.model_dump())

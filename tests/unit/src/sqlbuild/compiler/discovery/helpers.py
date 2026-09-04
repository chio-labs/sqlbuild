from pathlib import Path


def write_lifecycle_event_sink_project(*, project_dir: Path, exporter_config: str) -> None:
    (project_dir / "sinks").mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "filters"\nadapter = "duckdb"\n' + exporter_config,
        encoding="utf-8",
    )
    (project_dir / "sinks" / "publish.py").write_text(
        "from sqlbuild.sinks import lifecycle_event_sink\n"
        '@lifecycle_event_sink(event_kinds={"run", "statement"}, min_severity="info")\n'
        "def publish(event):\n    del event\n",
        encoding="utf-8",
    )

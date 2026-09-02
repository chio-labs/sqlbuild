from pathlib import Path


def write_event_exporter_project(*, project_dir: Path, exporter_config: str) -> None:
    (project_dir / "event_exporters").mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "filters"\nadapter = "duckdb"\n' + exporter_config,
        encoding="utf-8",
    )
    (project_dir / "event_exporters" / "publish.py").write_text(
        "from sqlbuild.event_exporters import event_exporter\n"
        '@event_exporter(event_kinds={"run", "statement"}, min_severity="info")\n'
        "def publish(event):\n    del event\n",
        encoding="utf-8",
    )

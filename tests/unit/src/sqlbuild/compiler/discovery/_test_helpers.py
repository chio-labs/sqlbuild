from pathlib import Path


def base_repo_files() -> dict[str, str]:
    return {
        "sqlbuild_project.yml": "name: demo\nadapter: duckdb\n",
    }


def write_repo_files(repo_root: Path, repo_files: dict[str, str]) -> None:
    for relative_path, content in repo_files.items():
        file_path: Path = repo_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

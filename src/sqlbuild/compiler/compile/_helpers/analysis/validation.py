"""Help for SQL the parser rejects."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import SQL_ANALYSIS_OPT_OUT_ENTRY
from sqlbuild.compiler.discovery.constants import (
    PROJECT_CONFIG_FILENAME,
    SETTINGS_SECTION,
    SQL_ANALYSIS_CONFIG_KEY,
)
from sqlbuild.errors.setting_help.main.join_helps import join_helps
from sqlbuild.errors.setting_help.main.model_header_help import model_header_help
from sqlbuild.errors.setting_help.main.setting_help import setting_help


def sql_analysis_opt_out_help(*, model_owned: bool = True) -> str:
    """Help for SQL the parser rejects: the exact header, project and single-run opt-outs."""

    report: str = (
        "if this SQL is valid for your warehouse, please report it so the parser can support it"
    )
    return join_helps(
        model_header_help(
            purpose="if this SQL is valid for your warehouse, skip SQL analysis for this model",
            entry=SQL_ANALYSIS_OPT_OUT_ENTRY,
            follow_up="and please report the SQL so the parser can support it",
        )
        if model_owned
        else report,
        setting_help(
            purpose="SQL analysis is on for this project; to turn it off for every model",
            file_name=PROJECT_CONFIG_FILENAME,
            section=SETTINGS_SECTION,
            key=SQL_ANALYSIS_CONFIG_KEY,
            value=False,
        ),
        "to skip SQL analysis for one run, use `--no-sql-analysis`",
    )

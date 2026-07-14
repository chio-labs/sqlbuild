"""SQL logging entrypoint."""

import logging

from sqlbuild.diagnostics.helpers.logging import log_sql as _log_sql


def log_sql(*, logger: logging.Logger, sql: str, action: str = "execute") -> None:
    """Log SQL passed to an adapter or connection."""

    log_result: None = _log_sql(logger=logger, sql=sql, action=action)
    return log_result

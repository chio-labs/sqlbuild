"""SQL logging entrypoint."""

import logging

from sqlbuild.diagnostics._helpers.logging import log_sql as _log_sql


def log_sql(
    *,
    logger: logging.Logger,
    sql: str,
    action: str = "execute",
    intent: str | None = None,
    query_id: str | None = None,
) -> None:
    """Log SQL passed to an adapter or connection."""

    log_result: None = _log_sql(
        logger=logger, sql=sql, action=action, intent=intent, query_id=query_id
    )
    return log_result

"""Archive-name parser entrypoint pending external integration."""

from sqlbuild.archives._helpers.naming import parse_archive_name as _parse_archive_name
from sqlbuild.archives.models import ParsedArchiveName


def parse_archive_name(name: str) -> ParsedArchiveName | None:
    """Parse one strict SQLBuild archive physical name."""

    return _parse_archive_name(name)

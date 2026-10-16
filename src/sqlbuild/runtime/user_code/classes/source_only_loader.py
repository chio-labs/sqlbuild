"""A source loader that neither reads nor writes cached bytecode."""

from importlib.machinery import SourceFileLoader
from types import CodeType


class SourceOnlyLoader(SourceFileLoader):
    """Compile a module from current source; whole-second pyc checks miss same-size edits."""

    def get_code(self, fullname: str) -> CodeType:
        source_path: str = self.get_filename(fullname)
        return self.source_to_code(self.get_data(source_path), source_path)

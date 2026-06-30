"""CLI document builder class."""

from __future__ import annotations

from sqlbuild.shared.helpers.cli_style import CliStyle


class CliDocument:
    """Build simple static CLI output with semantic styling."""

    def __init__(self, style: CliStyle) -> None:
        self._style: CliStyle = style
        self._lines: list[str] = []

    def header(self, text: str, *, suffix: str | None = None) -> None:
        rendered: str = self._style.title(text)
        if suffix is not None:
            rendered = f"{rendered}  {suffix}"
        self._lines.append(rendered)

    def blank(self) -> None:
        self._lines.append("")

    def field(self, label: str, value: str, *, value_padding: str = " ") -> None:
        self._lines.append(f"  {self._style.value(label)}:{value_padding}{value}")

    def fields(self, rows: tuple[tuple[str, str], ...], *, label_width: int | None = None) -> None:
        for label, value in rows:
            rendered_label: str = f"{label:<{label_width}}" if label_width is not None else label
            self._lines.append(f"  {self._style.value(rendered_label)} {value}")

    def section(self, text: str) -> None:
        self._lines.append(f"{self._style.section(text)}:")

    def title_section(self, text: str) -> None:
        self._lines.append(f"{self._style.title(text)}:")

    def line(self, text: str) -> None:
        self._lines.append(text)

    def items(self, values: tuple[str, ...]) -> None:
        for value in values:
            self._lines.append(f"  {self._style.object_name(value)}")

    def command_line(self, prefix: str, command: str, *, style_command: bool = True) -> None:
        rendered_command: str = self._style.command(command) if style_command else command
        self._lines.append(f"{prefix}{rendered_command}")

    def commands(
        self, commands: tuple[str, ...], *, numbered: bool = False, style_command: bool = True
    ) -> None:
        for index, command in enumerate(commands, start=1):
            prefix: str = f"  {index}. " if numbered else self._style.command("  ")
            self.command_line(prefix, command, style_command=style_command)

    def render(self, *, trailing_newline: bool = True) -> str:
        rendered: str = "\n".join(self._lines)
        return rendered + "\n" if trailing_newline else rendered

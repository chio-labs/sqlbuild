"""Fail when a built page links to a missing page or anchor on the same site."""

import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"] or "")


def route_for(dist: Path, file: Path) -> str:
    relative = "/" + file.relative_to(dist).as_posix()
    return relative.removesuffix("index.html")


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    pages: dict[str, PageParser] = {}
    for file in dist.rglob("*.html"):
        parser = PageParser()
        parser.feed(file.read_text())
        pages[route_for(dist, file)] = parser

    broken: list[str] = []
    for route, page in sorted(pages.items()):
        if route.startswith("/404"):
            continue
        for href in page.hrefs:
            url = urlsplit(href)
            if url.scheme or url.netloc:
                continue
            path = unquote(url.path) or route
            if not path.startswith("/"):
                path = route + path
            if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
                path += "/"
            target = pages.get(path)
            if target is None:
                if not (dist / path.lstrip("/")).exists():
                    broken.append(f"{route}: missing page {href}")
                continue
            fragment = unquote(url.fragment)
            if fragment and fragment != "_top" and fragment not in target.ids:
                broken.append(f"{route}: missing anchor {href}")

    for line in broken:
        print(line)
    print(f"{len(pages)} pages, {len(broken)} broken links")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())

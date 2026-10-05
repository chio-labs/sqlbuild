"""Random inputs for output capture text chunking tests."""

import random

_ALPHABET: tuple[str, ...] = (
    "a",
    "Z",
    " ",
    "\n",
    "é",
    "ß",
    "Ω",
    "订",
    "€",
    "✓",
    "📦",
    "🙂",
    "𝔸",
    "e\u0301",
    "\u0308",
)


def random_mixed_width_texts(*, seed: int, max_bytes: int, count: int) -> tuple[str, ...]:
    """Build texts whose encoded lengths land around multiples of the chunk limit."""

    generator: random.Random = random.Random(seed)
    return tuple(
        _random_mixed_width_text(generator=generator, max_bytes=max_bytes) for _ in range(count)
    )


def _random_mixed_width_text(*, generator: random.Random, max_bytes: int) -> str:
    target_bytes: int = max(
        0, max_bytes * generator.choice((0, 1, 1, 2, 3)) + generator.randint(-5, 5)
    )
    parts: list[str] = []
    size: int = 0
    while size < target_bytes:
        piece: str = generator.choice(_ALPHABET)
        parts.append(piece)
        size += len(piece.encode("utf-8"))
    return "".join(parts)

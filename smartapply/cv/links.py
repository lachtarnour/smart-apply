"""Split bullet text into plain text / hyperlink segments for rendering.

The HTML and DOCX renderers both need to wrap specific anchor words inside
hyperlinks. The matching logic is identical; only the output format differs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from markupsafe import Markup, escape

from smartapply.profile import BulletLink


@dataclass(frozen=True)
class BulletSegment:
    text: str
    url: str | None = None


def split_bullet_with_links(
    text: str,
    links: Iterable[BulletLink],
) -> list[BulletSegment]:
    """Return ordered segments where anchors are wrapped.

    - Each link's first non-overlapping anchor occurrence (case-insensitive)
      is wrapped. Subsequent occurrences and missing anchors fall through.
    - Always returns at least one segment.
    """
    matches: list[tuple[int, int, str]] = []
    lower = text.lower()
    for link in links:
        anchor = link.anchor.lower()
        if not anchor:
            continue
        start = 0
        while True:
            idx = lower.find(anchor, start)
            if idx == -1:
                break
            end = idx + len(anchor)
            if not any(s < end and idx < e for s, e, _ in matches):
                matches.append((idx, end, str(link.url)))
                break
            start = idx + 1
    matches.sort()

    segments: list[BulletSegment] = []
    cursor = 0
    for s, e, url in matches:
        if s > cursor:
            segments.append(BulletSegment(text[cursor:s]))
        segments.append(BulletSegment(text[s:e], url))
        cursor = e
    if cursor < len(text):
        segments.append(BulletSegment(text[cursor:]))
    if not segments:
        segments.append(BulletSegment(text))
    return segments


def render_bullet_html(text: str, links: Iterable[BulletLink]) -> Markup:
    """Render a bullet as escaped HTML with hyperlinks for each matched anchor."""
    parts: list[str] = []
    for segment in split_bullet_with_links(text, links):
        if segment.url:
            parts.append(
                f'<a href="{escape(segment.url)}">{escape(segment.text)}</a>'
            )
        else:
            parts.append(str(escape(segment.text)))
    return Markup("".join(parts))

"""Deterministic mechanics for translating one page of the handbook in place.

    .venv/bin/python -m tools.pagekit inspect pages/019.pdf     # regions, ids, places of interest
    .venv/bin/python -m tools.pagekit render  pages/019.pdf     # pages/019.png

A per-page script supplies the Ukrainian text per region id and calls TranslationJob.save().
The job redacts the English text over its full original extent (drawings and images stay),
lays the translation into the region's rectangle with the Avenir Next faces from fonts/,
shrinks the font until it fits, and reports every box that shrank or was left untranslated.
"""
from __future__ import annotations

import html as html_lib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

Rect = pymupdf.Rect
ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"


# --- text layer ----------------------------------------------------------------


@dataclass(frozen=True)
class Style:
    size: float
    color: str
    weight: int
    italic: bool

    @staticmethod
    def of_span(s: dict) -> "Style":
        font = s["font"].split("+")[-1]
        return Style(
            size=round(s["size"], 1),
            color=f"#{s['color']:06x}",
            weight=_weight(font),
            italic="Oblique" in font or "Italic" in font,
        )


def _weight(font: str) -> int:
    if any(w in font for w in ("Black", "Bold")) and "Semi" not in font and "Demi" not in font:
        return 700
    if any(w in font for w in ("Heavy", "Semibold", "SemiBold", "DemiBold", "Demi")):
        return 600
    if "Medium" in font:
        return 500
    return 400


@dataclass
class Span:
    text: str
    style: Style
    bbox: Rect
    font: str

    @property
    def is_bullet(self) -> bool:
        return "ZapfDingbats" in self.font or self.text.strip() in BULLET_GLYPHS


@dataclass
class Line:
    spans: list[Span]
    bbox: Rect

    @property
    def text(self) -> str:
        return normalize("".join(s.text for s in self.spans))

    @property
    def lead(self) -> Span:
        return max(self.spans, key=lambda s: len(s.text.strip()))

    @property
    def starts_with_bullet(self) -> bool:
        return self.spans[0].is_bullet or self.text[:1] in BULLET_GLYPHS

    def html(self, base: Style) -> str:
        out, prev = [], None
        for s in self.spans:
            if s.is_bullet:
                continue
            text = normalize(s.text)
            if prev is not None and s.bbox.x0 - prev.bbox.x1 > SPAN_GAP_FOR_SPACE and not prev.text.endswith(" "):
                text = " " + text
            text = html_lib.escape(text)
            if s.style.weight > base.weight:
                text = f"<b>{text}</b>"
            if s.style.italic and not base.italic:
                text = f"<i>{text}</i>"
            out.append(text)
            prev = s
        return "".join(out).strip()


def normalize(text: str) -> str:
    for a, b in NORMALIZE.items():
        text = text.replace(a, b)
    return re.sub(r"[ \t]+", " ", text)


# --- regions -------------------------------------------------------------------


@dataclass
class Region:
    """One translatable unit: a paragraph, heading, caption, bubble, or label."""

    id: str
    role: str
    lines: list[Line]
    rect: Rect
    style: Style
    center: bool = False
    shape: Rect | None = None  # the bubble or pill the text sits in, if any

    @property
    def obstacle(self) -> Rect:
        """What a neighbouring box must not run into: the whole shape, not only the text inside it."""
        return self.shape or self.rect

    @property
    def extent(self) -> Rect:
        """Where the English lettering actually is; redaction must cover all of it."""
        r = Rect()
        for l in self.lines:
            r |= l.bbox
        return r + (-1, -1, 1, 1)

    @property
    def english(self) -> str:
        parts = []
        for l in self.lines:
            t = l.text.lstrip(BULLET_GLYPHS).strip()
            if parts and parts[-1].endswith("-") and t[:1].islower():
                parts[-1] = parts[-1][:-1] + t
            else:
                parts.append(t)
        return " ".join(parts)

    @property
    def html(self) -> str:
        """The English text as the HTML the translation should mirror (inline <b>, <i>, bullets)."""
        paras, current = [], []
        for l in self.lines:
            if l.starts_with_bullet and current:
                paras.append(current)
                current = []
            current.append(l)
        if current:
            paras.append(current)
        out = []
        for lines in paras:
            text = " ".join(l.html(self.style) for l in lines)
            cls = ' class="li"' if lines[0].starts_with_bullet else ""
            prefix = "■&nbsp;" if lines[0].starts_with_bullet else ""
            out.append(f"<p{cls}>{prefix}{text}</p>")
        return "".join(out)

    @property
    def base_size(self) -> float:
        """Running text is set a little smaller across the whole book, so most boxes fit without per-box shrinking."""
        return round(self.style.size * BASE_SIZE_FACTOR.get(self.role, 1.0), 1)

    def css(self) -> str:
        return (
            f"body {{ font-family: {family(self.style.weight)}; font-size: {self.base_size}pt; color: {self.style.color}; "
            f"font-style: {'italic' if self.style.italic else 'normal'}; "
            f"line-height: {LINE_HEIGHT}; margin: 0; }}"
            f"p {{ margin: 0 0 {PARAGRAPH_GAP_EM}em 0; }} p.li {{ margin-left: 0.9em; text-indent: -0.9em; }}"
            f"b {{ font-family: {family(600)}; }} i {{ font-style: italic; }}"
            + ("body { text-align: center; }" if self.role in CENTERED_ROLES else "")
        )

    def describe(self) -> str:
        r = self.rect
        style = f"{self.style.size}pt {self.style.color} w{self.style.weight}{' italic' if self.style.italic else ''}"
        return f"{self.id:4} {self.role:15} ({r.x0:.0f},{r.y0:.0f},{r.x1:.0f},{r.y1:.0f}) {style:28} {self.english[:70]!r}"


class Fonts:
    """The Cyrillic replacement faces in fonts/, served to insert_htmlbox as one family."""

    def __init__(self, directory: Path = FONT_DIR):
        self.directory = directory
        self.archive = pymupdf.Archive(directory)

    def css(self) -> str:
        return "\n".join(
            f"@font-face {{ font-family: {family(w)}; src: url({file}); font-style: {st}; }}"
            for file, (w, st) in FACES.items()
            if (self.directory / file).exists()
        )


def family(weight: int) -> str:
    """One font family per weight: the layout engine only distinguishes normal and bold inside a family."""
    return f"an{min(FACE_WEIGHTS, key=lambda w: abs(w - weight))}"


class Page:
    """Text regions and places of interest of one single-page PDF."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.doc = pymupdf.open(self.path)
        self.page = self.doc[0]
        self.drawings = _visible_drawings(self.page)
        self._textless: pymupdf.Pixmap | None = None
        self.regions: list[Region] = self._regions()

    def region(self, region_id: str) -> Region:
        for r in self.regions:
            if r.id == region_id:
                return r
        raise KeyError(region_id)

    # -- analysis ---------------------------------------------------------------

    def _lines(self) -> list[Line]:
        lines = []
        for b in self.page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for l in b["lines"]:
                spans = [
                    Span(s["text"], Style.of_span(s), Rect(s["bbox"]), s["font"])
                    for s in l["spans"]
                    if s["text"].strip()
                ]
                if spans:
                    lines.append(Line(spans, Rect(l["bbox"])))
        return lines

    def _white_shapes(self) -> list[Rect]:
        return [
            d["rect"]
            for d in self.drawings
            if d.get("fill") is not None
            and min(d["fill"]) > 0.98
            and BUBBLE_MIN_W <= d["rect"].width <= BUBBLE_MAX_W
            and d["rect"].height >= BUBBLE_MIN_H
        ]

    def _pills(self) -> list[Rect]:
        return [
            d["rect"]
            for d in self.drawings
            if d.get("fill") is not None and max(d["fill"]) < 0.98 and d["rect"].height <= PILL_MAX_H and d["rect"].width >= 15
        ]

    def _regions(self) -> list[Region]:
        lines = self._lines()
        white, pills = self._white_shapes(), self._pills()
        groups: list[tuple[str, list[Line], Rect | None]] = []

        def role_of(line: Line) -> tuple[str, Rect | None]:
            s = line.lead.style
            c = _center(line.bbox)
            if "Gotham" in line.lead.font and line.bbox.y0 < RUNNING_HEADER_MAX_Y:
                return "running-header", None
            if "Gotham" in line.lead.font and line.bbox.y0 > PAGE_NUMBER_MIN_Y:
                return "page-number", None
            for shape in white:
                if c in shape:
                    return "bubble", shape
            if s.color == "#ffffff":
                for pill in pills:
                    if c in pill:
                        return "label", pill
                return "label", None
            if s.color in HEADING_COLORS and s.weight >= 500 and s.size >= 9.8:
                return "heading", None
            if line.bbox.x1 < SIDEBAR_MAX_X:
                return "sidebar", None
            if s.weight >= 600 and s.italic:
                return "caption", None
            if s.italic:
                return "story", None
            if s.weight >= 600 and s.size >= 9.8:
                return "panel-title", None
            return "body", None

        for line in sorted(lines, key=lambda l: (round(l.bbox.y0), l.bbox.x0)):
            for piece in _split_by_shape(line, white, pills):
                role, shape = role_of(piece)
                # Two bubbles or two caption columns interleave in y order, so look at every open group.
                home = next((g for g in reversed(groups[-OPEN_GROUPS:]) if _same_group(g, piece, role, shape)), None)
                if home:
                    home[1].append(piece)
                else:
                    groups.append((role, [piece], shape))

        regions = []
        for n, (role, glines, shape) in enumerate(sorted(groups, key=lambda g: (round(g[1][0].bbox.y0 / ROW_BIN), g[1][0].bbox.x0)), 1):
            extent = Rect()
            for l in glines:
                extent |= l.bbox
            if role == "bubble":
                rect = self._inscribed(shape)
            elif role == "label" and shape is not None:
                rect = shape + (shape.height * PILL_TIP_FRACTION, 0, -shape.height * PILL_TIP_FRACTION, 0)
            else:
                rect = extent + (0, 0, ROOM_RIGHT, ROOM_BELOW)
            if role in ("heading", "panel-title") and extent.x0 >= SIDEBAR_MAX_X:
                rect.x1 = max(rect.x1, COLUMN_RIGHT)
            regions.append(Region(f"r{n:02d}", role, glines, rect, glines[0].lead.style, center=role in CENTERED_ROLES, shape=shape))
        return _separated(regions)

    def _inscribed(self, shape: Rect) -> Rect:
        """Largest text-shaped white rectangle around the bubble's centre, measured on a render without text."""
        if self._textless is None:
            scratch = pymupdf.open(self.path)
            scratch[0].add_redact_annot(scratch[0].rect)
            scratch[0].apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
            self._textless = scratch[0].get_pixmap(matrix=pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE))
        pix = self._textless
        cx, cy = int(shape.x0 + shape.width / 2) * RENDER_SCALE, int(shape.y0 + shape.height / 2) * RENDER_SCALE
        white = lambda x, y: all(c > WHITE_LEVEL for c in pix.pixel(x, y)[:3])
        best = Rect(cx - 1, cy - 1, cx + 1, cy + 1)
        for half_height in range(2, int(shape.height * RENDER_SCALE / 2)):
            y0, y1 = cy - half_height, cy + half_height
            if y0 < 0 or y1 >= pix.height or not all(white(cx, y) for y in range(y0, y1)):
                break
            x0 = x1 = cx
            while x0 > 0 and all(white(x0 - 1, y) for y in range(y0, y1)):
                x0 -= 1
            while x1 < pix.width - 1 and all(white(x1 + 1, y) for y in range(y0, y1)):
                x1 += 1
            candidate = Rect(x0, y0, x1, y1)
            if candidate.width >= candidate.height * TEXT_BOX_MIN_ASPECT and candidate.get_area() > best.get_area():
                best = candidate
        return best / RENDER_SCALE + (BUBBLE_PADDING, BUBBLE_PADDING, -BUBBLE_PADDING, -BUBBLE_PADDING)

    def illustrations(self) -> list[tuple[Rect, int]]:
        """Drawing clusters large enough to be artwork, with the count of real-text lines inside."""
        page_rect = self.page.rect
        kept = [
            d for d in self.drawings
            if d["rect"].width >= 1.5 and d["rect"].height >= 1.5
            and not (d["rect"].width > page_rect.width * 0.8 and d["rect"].height > page_rect.height * 0.8)
        ]
        clusters = [r for r in self.page.cluster_drawings(drawings=kept) if r.width >= ART_MIN and r.height >= ART_MIN] if kept else []
        lines = self._lines()
        return [(c, sum(1 for l in lines if _center(l.bbox) in c)) for c in clusters]

    def places_of_interest(self) -> list[str]:
        notes = []
        for r in self.regions:
            if r.role == "bubble":
                notes.append(f"{r.id}: thought/speech bubble, {r.style.size}pt; box is the widest white rectangle inside the cloud, check the render")
            elif r.role == "label":
                notes.append(f"{r.id}: white label on a coloured pill ({r.rect.width:.0f}pt wide); will shrink, text is centred")
            elif r.role == "caption" and r.rect.width < NARROW_PT:
                notes.append(f"{r.id}: caption in a narrow box ({r.rect.width:.0f}pt); side-by-side captions must not grow into each other")
            elif r.style.size < SMALL_TEXT_PT:
                notes.append(f"{r.id}: small text ({r.style.size}pt) inside artwork")
            elif r.rect.width < NARROW_PT and r.role not in ("page-number", "running-header", "heading", "panel-title"):
                notes.append(f"{r.id}: narrow box ({r.rect.width:.0f}pt), likely to shrink")
        for rect, n in self.illustrations():
            where = f"({rect.x0:.0f},{rect.y0:.0f},{rect.x1:.0f},{rect.y1:.0f})"
            if n:
                notes.append(f"illustration at {where} contains {n} line(s) of real text (translatable regions above)")
            else:
                notes.append(f"illustration at {where} has no text layer: check the render for vectorised lettering")
        if any(t.bbox for t in self.page.find_tables().tables):
            notes.append("table detected: cell heights are fixed by artwork rules, translate cell by cell")
        return notes

    def render(self, out: Path | None = None, dpi: int = 100) -> Path:
        out = out or self.path.with_suffix(".png")
        self.page.get_pixmap(dpi=dpi).save(out)
        return out

    def inspect_text(self) -> str:
        fonts = sorted({f[3].split("+")[-1] for f in self.page.get_fonts()})
        lines = [f"{self.path}  {self.page.rect.width:.0f}x{self.page.rect.height:.0f}pt  fonts: {', '.join(fonts)}", "", "Regions (reading order):"]
        lines += [r.describe() for r in self.regions]
        lines += ["", "Places of interest:"] + [f"- {n}" for n in self.places_of_interest()]
        return "\n".join(lines)


# --- applying a translation ------------------------------------------------------


@dataclass
class Placement:
    rect: Rect
    scale: float
    spare_height: float


@dataclass
class Report:
    placements: dict[str, Placement] = field(default_factory=dict)
    untranslated: list[str] = field(default_factory=list)
    leftover_english: list[str] = field(default_factory=list)
    drawings_before: int = 0
    drawings_after: int = 0

    def tight(self) -> list[str]:
        return [f"{k}: scale {p.scale:.2f}" for k, p in self.placements.items() if p.scale < TIGHT_SCALE]

    def __str__(self) -> str:
        out = [f"{k}: scale {p.scale:.2f}, spare {p.spare_height:.1f}pt" for k, p in self.placements.items()]
        if self.untranslated:
            out.append("untranslated (left in English): " + ", ".join(self.untranslated))
        if self.leftover_english:
            out.append("English still on page: " + ", ".join(self.leftover_english))
        out.append(f"drawings: {self.drawings_before} before, {self.drawings_after} after")
        return "\n".join(out)


@dataclass
class _Item:
    key: str
    regions: list[Region]
    html: str
    rect: Rect
    center: bool


class TranslationJob:
    def __init__(self, path: Path | str, fonts: Fonts | None = None):
        self.page = Page(path)
        self.fonts = fonts or Fonts()
        self._items: list[_Item] = []

    def set(self, region_ids: str | list[str], html: str, rect: Rect | None = None, center: bool | None = None) -> None:
        """Translate one region, or several regions laid into one shared box (their union by default)."""
        ids = [region_ids] if isinstance(region_ids, str) else list(region_ids)
        regions = [self.page.region(i) for i in ids]
        if rect is None:
            rect = Rect()
            for r in regions:
                rect |= r.rect
        self._items.append(_Item("+".join(ids), regions, html, Rect(rect), regions[0].center if center is None else center))

    def save(self, out: Path | str, preview: Path | str | None = None) -> Report:
        report = Report(drawings_before=len(self.page.page.get_drawings()))
        doc = pymupdf.open(self.page.path)
        page = doc[0]
        done = {r.id for it in self._items for r in it.regions}
        report.untranslated = [r.english for r in self.page.regions if r.id not in done]

        for it in self._items:
            for r in it.regions:
                page.add_redact_annot(r.extent | it.rect if len(it.regions) == 1 else r.extent)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)

        for it in self._items:
            css = self.fonts.css() + it.regions[0].css()
            rect = it.rect
            if it.center:
                rect = _vertically_centered(rect, it.html, css, self.fonts.archive)
            spare, scale = page.insert_htmlbox(rect, it.html, css=css, archive=self.fonts.archive, scale_low=0)
            report.placements[it.key] = Placement(rect, scale, spare)

        doc.subset_fonts()
        doc.save(out, garbage=3, deflate=True)
        result = pymupdf.open(out)[0]
        report.drawings_after = len(result.get_drawings())
        report.leftover_english = sorted({w for w in re.findall(r"[A-Za-z]{2,}", result.get_text()) if w not in KEEP_ENGLISH})
        if preview:
            result.get_pixmap(dpi=100).save(preview)
        return report


# --- geometry helpers ------------------------------------------------------------


def _center(r: Rect) -> pymupdf.Point:
    return pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)


def _split_by_shape(line: Line, white: list[Rect], pills: list[Rect]) -> list[Line]:
    """A line whose spans fall into different shapes (caption | pill | caption) becomes one line per shape."""
    def key(s: Span):
        c = _center(s.bbox)
        for i, shape in enumerate(white + pills):
            if c in shape:
                return i
        return -1

    pieces: list[list[Span]] = []
    for s in line.spans:
        if pieces and key(pieces[-1][-1]) == key(s) and s.bbox.x0 - pieces[-1][-1].bbox.x1 < COLUMN_GAP:
            pieces[-1].append(s)
        else:
            pieces.append([s])
    out = []
    for spans in pieces:
        r = Rect()
        for s in spans:
            r |= s.bbox
        out.append(Line(spans, r))
    return out


def _separated(regions: list[Region]) -> list[Region]:
    """Trailing spaces widen a text extent; cut a box short where it would run into a neighbour to its right."""
    for r in regions:
        for other in regions:
            o = other.obstacle
            if other is r or o.x0 <= r.rect.x0:
                continue
            if o.x0 < r.rect.x1 and o.y0 < r.rect.y1 and r.rect.y0 < o.y1:
                r.rect.x1 = o.x0 - COLUMN_GAP / 2
    return regions


def _same_group(group, line: Line, role: str, shape: Rect | None) -> bool:
    prev_role, prev_lines, prev_shape = group
    if role != prev_role or shape != prev_shape:
        return False
    if role in ("running-header", "page-number", "label"):
        return False
    last = prev_lines[-1]
    gap = line.bbox.y0 - last.bbox.y1
    overlaps = line.bbox.x0 < last.bbox.x1 + COLUMN_GAP and last.bbox.x0 < line.bbox.x1 + COLUMN_GAP
    same_size = abs(line.lead.style.size - last.lead.style.size) < 0.6
    new_paragraph = gap > PARAGRAPH_GAP and role in ("body", "sidebar", "story")
    return -LINE_GAP < gap <= LINE_GAP and overlaps and same_size and not new_paragraph


def _vertically_centered(rect: Rect, html: str, css: str, archive: pymupdf.Archive) -> Rect:
    scratch = pymupdf.open().new_page(width=1000, height=1000)
    spare, _ = scratch.insert_htmlbox(rect, html, css=css, archive=archive, scale_low=0)
    return rect + (0, spare / 2, 0, 0)


def _visible_drawings(page: pymupdf.Page) -> list[dict]:
    """Drawings with rects cut to the clip paths in force; get_drawings reports unclipped extents."""
    out, clip_stack = [], []
    for d in page.get_drawings(extended=True):
        level = d.get("level", 0)
        while clip_stack and clip_stack[-1][0] >= level:
            clip_stack.pop()
        if d["type"] == "clip":
            clip_stack.append((level, Rect(d["scissor"]) if d.get("scissor") else page.rect))
            continue
        if d["type"] == "group":
            continue
        r = Rect(d["rect"]) & page.rect
        for _, scissor in clip_stack:
            r &= scissor
        if not r.is_empty:
            d["rect"] = r
            out.append(d)
    return out


# --- command line -----------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("inspect", "render"):
        sys.exit(__doc__)
    page = Page(argv[1])
    if argv[0] == "inspect":
        print(page.inspect_text())
    else:
        print(page.render())


FACES = {
    "AvenirNext-Regular.ttf": (400, "normal"),
    "AvenirNext-Italic.ttf": (400, "italic"),
    "AvenirNext-Medium.ttf": (500, "normal"),
    "AvenirNext-MediumItalic.ttf": (500, "italic"),
    "AvenirNext-DemiBold.ttf": (600, "normal"),
    "AvenirNext-DemiBoldItalic.ttf": (600, "italic"),
    "AvenirNext-Bold.ttf": (700, "normal"),
    "AvenirNext-BoldItalic.ttf": (700, "italic"),
}
NORMALIZE = {"ﬁ": "fi", "ﬂ": "fl", "\t": " ", "\x07": " ", "\xad": "", "​": "", " ": " ", " ": " "}
BULLET_GLYPHS = "■•▪–"
HEADING_COLORS = {"#8387aa", "#378ac0", "#8dc63f"}
CENTERED_ROLES = {"bubble", "label"}
KEEP_ENGLISH = {"ICBC", "GLP", "STOP", "YIELD", "ONE", "WAY", "km", "kg"}
LINE_HEIGHT = 1.211
BASE_SIZE_FACTOR = {"body": 0.95, "sidebar": 0.95, "story": 0.95}
PARAGRAPH_GAP_EM = 0.6
SPAN_GAP_FOR_SPACE = 1.5
SIDEBAR_MAX_X = 170.0
RUNNING_HEADER_MAX_Y = 60.0
PAGE_NUMBER_MIN_Y = 660.0
ROW_BIN = 8.0
LINE_GAP = 7.5
PARAGRAPH_GAP = 4.0
COLUMN_GAP = 12.0
COLUMN_RIGHT = 450.0
OPEN_GROUPS = 6
ROOM_RIGHT = 3.0
ROOM_BELOW = 2.0
BUBBLE_MIN_W, BUBBLE_MAX_W, BUBBLE_MIN_H = 40.0, 200.0, 25.0
BUBBLE_PADDING = 1.5
WHITE_LEVEL = 245
PILL_TIP_FRACTION = 0.5  # arrow tips on the "or" pills are about half the pill height wide
TEXT_BOX_MIN_ASPECT = 2.0
RENDER_SCALE = 4
FACE_WEIGHTS = (400, 500, 600, 700)
PILL_MAX_H = 30.0
ART_MIN = 40.0
SMALL_TEXT_PT = 7.0
NARROW_PT = 120.0
TIGHT_SCALE = 0.9

if __name__ == "__main__":
    main()

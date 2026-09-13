"""Reflow translated pages into one HTML document per chapter for the GitHub Pages site.

    .venv/bin/python -m tools.sitekit            # every section and docs/sitemap.xml
    .venv/bin/python -m tools.sitekit 3          # docs/03-signs-signals-and-road-markings.html, docs/img/03/*.png

The text comes from translations/NNN.json, the structure (headings, captions, body, boxes) from the
region roles pagekit derives from the English page, and the pictures are crops of the translated
page PDF around each drawing cluster. Page layout is not reproduced: the output is a linear
document. A drawing cluster that holds paragraph text is a box and becomes an aside placed where
it sits beside the main text; one that holds only lettering is a picture and the lettering stays
in the crop. Rows of captioned pictures become galleries.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import pymupdf

from tools.pagekit import Page, Rect, Region


# --- blocks ----------------------------------------------------------------------


def _text(html: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", html)).replace("\xa0", " ").strip()


def _slug(english: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", english.lower()).strip("-")


@dataclass(frozen=True)
class Heading:
    level: int
    id: str
    html: str

    @property
    def text(self) -> str:
        return _text(self.html)

    def render(self) -> str:
        return f'<h{self.level} id="{self.id}">{self.text}</h{self.level}>'


@dataclass(frozen=True)
class Paragraph:
    html: str
    kind: str

    def render(self) -> str:
        return self.html if self.kind == "body" else self.html.replace("<p>", f'<p class="{self.kind}">')


@dataclass(frozen=True)
class PageStart:
    """Where a printed page begins; an anchor so the HTML and the PDF can refer to the same place."""

    label: str

    def render(self) -> str:
        return f'<span id="p{self.label}" class="page"></span>'


@dataclass(frozen=True)
class Pill:
    """The "or" between two pictured choices."""

    html: str

    @property
    def text(self) -> str:
        return _text(self.html)

    def render(self) -> str:
        return f'<span class="or">{self.text}</span>'


@dataclass(frozen=True)
class Choice:
    """One side of an "or" comparison that has no picture."""

    html: str

    def render(self) -> str:
        return f'<p class="choice">{_text(self.html)}</p>'


@dataclass(frozen=True)
class Figure:
    page: int
    index: int
    rect: Rect
    caption_html: str

    @property
    def caption(self) -> str:
        return _text(self.caption_html)

    @property
    def image(self) -> str:
        return f"{self.page:03d}-{self.index:02d}.png"

    @property
    def clip(self) -> Rect:
        return self.rect + (-FIGURE_PAD, -FIGURE_PAD, FIGURE_PAD, FIGURE_PAD)

    def render(self, image_dir: str, context: str) -> str:
        """The pixel size is declared so the page keeps its layout while pictures load; otherwise a restored
        reading position drifts as each picture above it arrives."""
        alt = html_lib.escape(self.caption or context, quote=True)
        basis = max(FIGURE_MIN_PX, round(self.rect.width * PX_PER_PT))
        width, height = round(self.clip.width * FIGURE_DPI / 72), round(self.clip.height * FIGURE_DPI / 72)
        caption = f"<figcaption>{self.caption_html}</figcaption>" if self.caption_html else ""
        return (f'<figure style="flex-basis:{basis}px"><img src="{image_dir}/{self.image}" alt="{alt}" '
                f'width="{width}" height="{height}" loading="lazy">{caption}</figure>')

    def crop(self, source: Path, out: Path) -> None:
        pymupdf.open(source)[0].get_pixmap(clip=self.clip, dpi=FIGURE_DPI).save(out)


@dataclass(frozen=True)
class Aside:
    """A box on the page: a sidebar note, a driving tip, a strategies panel, a story."""

    kind: str
    title_html: str
    blocks: tuple[Block, ...]

    @property
    def title(self) -> str:
        return _text(self.title_html)

    def render(self, image_dir: str, context: str) -> str:
        title = f"<h4>{self.title}</h4>" if self.title_html else ""
        return f'<aside class="{self.kind}">{title}{render_blocks(self.blocks, image_dir, context)}</aside>'


@dataclass(frozen=True)
class Cell:
    html: str
    rowspan: int
    colspan: int

    @property
    def text(self) -> str:
        return _text(self.html)

    def render(self, tag: str) -> str:
        attrs = (f' rowspan="{self.rowspan}"' if self.rowspan > 1 else "") + (f' colspan="{self.colspan}"' if self.colspan > 1 else "")
        single = re.fullmatch(r"<p>(.*)</p>", self.html)
        return f"<{tag}{attrs}>{single.group(1) if single else self.html}</{tag}>"


@dataclass(frozen=True)
class Table:
    header: tuple[Cell, ...]
    rows: tuple[tuple[Cell, ...], ...]

    def render(self) -> str:
        head = "<tr>" + "".join(c.render("th") for c in self.header) + "</tr>"
        body = "".join("<tr>" + "".join(c.render("td") for c in row) + "</tr>" for row in self.rows)
        return f"<table><thead>{head}</thead><tbody>{body}</tbody></table>"


Block = Heading | Paragraph | PageStart | Pill | Choice | Figure | Aside | Table


def render_blocks(blocks: tuple[Block, ...] | list[Block], image_dir: str, context: str) -> str:
    """Consecutive pictures and pills form one gallery; lists split across translation entries rejoin."""
    out: list[str] = []
    gallery: list[str] = []

    def flush() -> None:
        if gallery:
            out.append('<div class="gallery">' + "".join(gallery) + "</div>")
            gallery.clear()

    for b in blocks:
        if isinstance(b, Figure):
            gallery.append(b.render(image_dir, context))
        elif isinstance(b, (Pill, Choice)):
            gallery.append(b.render())
        else:
            flush()
            if isinstance(b, Heading):
                context = b.text
            out.append(b.render(image_dir, context) if isinstance(b, Aside) else b.render())
    flush()
    return "\n".join(out).replace("</ul>\n<ul>", "")


# --- one translated page ---------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    """One translation entry: the Ukrainian HTML and the English regions it replaces."""

    regions: list[Region]
    html: str

    @property
    def lead(self) -> Region:
        return self.regions[0]

    @property
    def rect(self) -> Rect:
        """Where the English lettering is; the translation box may be widened or, in a bubble, unmeasurable."""
        r = Rect()
        for region in self.regions:
            r |= region.extent
        return r

    @property
    def center(self) -> pymupdf.Point:
        return (self.rect.top_left + self.rect.bottom_right) / 2

    @property
    def is_caption(self) -> bool:
        s = self.lead.style
        return self.lead.role == "caption" or (
            self.lead.role in CAPTION_ROLES and s.size <= CAPTION_MAX_PT and s.weight >= CAPTION_MIN_WEIGHT)

    @property
    def is_box_text(self) -> bool:
        return self.lead.role in BOX_TEXT_ROLES or (self.lead.role == "body" and self.lead.style.size >= BOX_TEXT_MIN_PT)

    def is_title_of(self, box: Rect) -> bool:
        shape = self.lead.shape
        return self.lead.role == "label" and shape is not None and shape.width >= box.width * TITLE_WIDTH_FRACTION

    @property
    def is_pill(self) -> bool:
        return self.lead.role == "label" and self.lead.shape is not None

    def paragraph(self) -> Paragraph:
        return Paragraph(self.clean_html(), PARAGRAPH_KINDS.get(self.lead.role, "body"))

    def clean_html(self) -> str:
        """Layout styling written for the PDF box is dropped; bullet paragraphs become list items."""
        html = re.sub(r' style="[^"]*"', "", self.html)
        html = re.sub(r'<p class="li">■&nbsp;(.*?)</p>', r"<li>\1</li>", html)
        return re.sub(r"((?:<li>.*?</li>)+)", r"<ul>\1</ul>", html)


class TranslatedPage:
    def __init__(self, root: Path, number: int, section_title: str, outline: dict[str, int]):
        self.number = number
        self.outline = outline
        self.source = root / "pages" / f"{number:03d}.pdf"
        self.translated = root / "pages" / f"{number:03d}.ua.pdf"
        self.page = Page(self.source)
        data = json.loads((root / "translations" / f"{number:03d}.json").read_text())
        self.entries = [Entry([self.page.region(i) for i in e["ids"]], e["html"]) for e in data["regions"]]
        self.section_title = section_title

    @cached_property
    def tables(self) -> list:
        return self.page.page.find_tables().tables

    def title_entry(self) -> Entry | None:
        """The entry that states the section title: the chapter bar, or the heading a front or back matter page opens with."""
        wanted = _normalized(self.section_title)
        return next((e for e in self.entries if _normalized(e.lead.english) == wanted), None)

    @property
    def label(self) -> str | None:
        """The printed page number; front matter pages have none."""
        return next((r.english for r in self.page.regions if r.role == "page-number"), None)

    def blocks(self) -> list[Block]:
        contents = self._contents_box()
        title = self.title_entry()
        entries = [e for e in self.entries
                   if e.lead.role not in DROPPED_ROLES and e is not title and not (contents and e.center in contents)]
        blocks = self._arrange(entries, self.page.page.rect)
        numbered: list[Block] = [PageStart(self.label)] if self.label else []
        count = 0
        for b in blocks:
            if isinstance(b, Figure):
                count += 1
                b = Figure(b.page, count, b.rect, b.caption_html)
            elif isinstance(b, Aside):
                inner = []
                for x in b.blocks:
                    if isinstance(x, Figure):
                        count += 1
                        x = Figure(x.page, count, x.rect, x.caption_html)
                    inner.append(x)
                b = Aside(b.kind, b.title_html, tuple(inner))
            numbered.append(b)
        return numbered

    def _arrange(self, entries: list[Entry], container: Rect) -> list[Block]:
        """Reading order inside one rectangle: main text top to bottom; a box, a picture, or a row of
        pictures after the text it sits beside; pictures in a row left to right."""
        placed: list[tuple[float, float, int, Block]] = []

        def place(y: float, x: float, block: Block) -> None:
            placed.append((y, x, len(placed), block))

        pictures: list[Rect] = []
        loose = list(entries)
        for cluster, text_lines in _stacked(self.page.pictures(container, FIGURE_MIN_PT)):
            if _fills(cluster, container):
                continue
            inside = [e for e in loose if e.center in cluster]
            loose = [e for e in loose if e not in inside]
            found = None
            if any(e.lead.role == "label" for e in inside):
                found = next((t for t in self.tables if _covers(Rect(t.bbox), cluster)), None)
            if found is not None:
                place(cluster.y0, cluster.x0, self._table(found, inside))
            elif any(e.is_box_text or e.is_title_of(cluster) for e in inside) and _text_share(inside, cluster) >= BOX_TEXT_MIN_SHARE:
                place(cluster.y1, cluster.x0, self._box(inside, cluster))
            elif inside or text_lines == 0:
                pictures.append(cluster)
        captions: dict[int, list[Entry]] = {}
        unattached: list[Entry] = []
        pills: list[Entry] = []
        for e in loose:
            if e.lead.role == "heading":
                place(e.rect.y0, e.rect.x0, Heading(self._heading_level(e), _slug(e.lead.english), e.clean_html()))
            elif e.is_caption and (picture := _picture_above(e.rect, pictures)) is not None:
                captions.setdefault(pictures.index(picture), []).append(e)
            elif e.is_caption:
                unattached.append(e)
            elif e.is_pill:
                pills.append(e)
            else:
                place(e.rect.y0, e.rect.x0, e.paragraph())
        figures: list[tuple[Rect, Entry | None]] = []
        for i, picture in enumerate(pictures):
            figures.extend(_split(picture, captions[i]) if i in captions else [(picture, None)])
        for row in _rows(figures):
            bottom = max(r.y1 for r, _ in row)
            for rect, e in row:
                place(bottom, rect.x0, Figure(self.number, 0, rect, e.clean_html() if e else ""))
            for pill in [p for p in pills if any(e and _overlap_y(p.rect, e.rect) for _, e in row)]:
                pills.remove(pill)
                place(bottom, pill.rect.x0, Pill(pill.clean_html()))
        for pill in pills:
            choices = [c for c in unattached if _overlap_y(pill.rect, c.rect)]
            bottom = max([c.rect.y1 for c in choices], default=pill.rect.y1)
            place(bottom, pill.rect.x0, Pill(pill.clean_html()))
            for c in choices:
                unattached.remove(c)
                place(bottom, c.rect.x0, Choice(c.clean_html()))
        for e in unattached:
            place(e.rect.y0, e.rect.x0, e.paragraph())
        return [b for _, _, _, b in sorted(placed, key=lambda p: p[:3])]

    def _heading_level(self, e: Entry) -> int:
        """The book's outline says how headings nest; a heading the outline lacks is placed by its size."""
        size = e.lead.style.size
        by_size = 2 if size >= SECTION_HEADING_MIN_PT else 3 if size >= SUBSECTION_HEADING_MIN_PT else 4
        return self.outline.get(_normalized(e.lead.english), by_size)

    def _box(self, inside: list[Entry], cluster: Rect) -> Aside:
        title = next((e for e in inside if e.is_title_of(cluster)), None)
        title = title or next((e for e in inside if e.lead.role == "panel-title"), None)
        body = [e for e in inside if e is not title]
        if title is not None and title.lead.role == "label":
            kind = BOX_KINDS[title.lead.english.lower()]
        elif any(e.lead.role == "story" for e in body):
            kind = "story"
        elif title is not None:
            kind = "panel"
        else:
            kind = "note"
        return Aside(kind, title.clean_html() if title else "", tuple(self._arrange(body, cluster)))

    def _table(self, found, entries: list[Entry]) -> Table:
        """Cells come from the ruling lines; a cell that spans columns but holds text in several of them is a
        header drawn as one band, so it is split per column."""
        bounds = [None] * found.col_count
        for row in found.rows:
            for j, c in enumerate(row.cells):
                if c is not None and bounds[j] is None:
                    bounds[j] = c[0]
        bounds = [x for x in bounds if x is not None] + [found.bbox[2]]
        row_rects = [Rect(r.bbox) for r in found.rows]

        def column(x: float) -> int:
            return max(k for k in range(len(bounds) - 1) if bounds[k] <= x + CELL_TOLERANCE_PT)

        def cells(boxes, first_row_below: int) -> tuple[Cell, ...]:
            out = []
            for j, c in enumerate(boxes):
                if c is None:
                    continue
                rect = Rect(c)
                colspan = 1 + sum(1 for k in range(j + 1, len(bounds) - 1) if bounds[k] < rect.x1 - CELL_TOLERANCE_PT)
                rowspan = 1 + sum(1 for r in row_rects[first_row_below:]
                                  if r.y0 >= rect.y0 - CELL_TOLERANCE_PT and r.y1 <= rect.y1 + CELL_TOLERANCE_PT)
                inside = [e for e in entries if e.center in rect]
                columns = sorted({column(e.center.x) for e in inside})
                if colspan > 1 and len(columns) > 1:
                    out.extend(Cell(_joined([e for e in inside if column(e.center.x) == k]), rowspan, 1) for k in range(j, j + colspan))
                else:
                    out.append(Cell(_joined(inside), rowspan, colspan))
            return tuple(out)

        if found.header.external:
            return Table(cells(found.header.cells, 0), tuple(cells(r.cells, i + 1) for i, r in enumerate(found.rows)))
        return Table(cells(found.rows[0].cells, 1), tuple(cells(r.cells, i + 2) for i, r in enumerate(found.rows[1:])))

    def _contents_box(self) -> Rect | None:
        """The "in this chapter" box on a chapter's first page; the site generates its own contents list."""
        label = next((e for e in self.entries if e.lead.english.lower() == CONTENTS_LABEL), None)
        if label is None:
            return None
        return next(rect for rect, _ in self.page.illustrations(FIGURE_MIN_PT) if label.center in rect)


def _normalized(english: str) -> str:
    return english.strip().lower().replace("\u2019", "'")


def _joined(entries: list[Entry]) -> str:
    return "".join(e.clean_html() for e in sorted(entries, key=lambda e: (e.rect.y0, e.rect.x0))).replace("</ul><ul>", "")


def _text_share(entries: list[Entry], cluster: Rect) -> float:
    """How much of a cluster its own text covers: a note or panel is mostly text, a diagram is mostly drawing."""
    return sum(e.rect.get_area() for e in entries if e.is_box_text or e.lead.role in ("caption", "label")) / cluster.get_area()


def _covers(a: Rect, b: Rect) -> bool:
    """Two rectangles are the same thing when their overlap is most of the larger one."""
    return (a & b).get_area() >= COVER_FRACTION * max(a.get_area(), b.get_area())


def _fills(inner: Rect, container: Rect) -> bool:
    """The border and fill of a box cluster together as a cluster of their own; that is the box, not a picture in it."""
    return inner.width >= container.width * BACKGROUND_FRACTION and inner.height >= container.height * BACKGROUND_FRACTION


def _overlap_y(a: Rect, b: Rect) -> bool:
    return a.y0 < b.y1 and a.y1 > b.y0


def _picture_above(caption: Rect, pictures: list[Rect]) -> Rect | None:
    above = [p for p in pictures if p.x0 < caption.x1 and p.x1 > caption.x0 and p.y1 <= caption.y0 + CAPTION_OVERLAP_PT]
    return min(above, key=lambda p: caption.y0 - p.y1, default=None)


def _split(picture: Rect, captions: list[Entry]) -> list[tuple[Rect, Entry]]:
    """Pictures drawn close together cluster as one; the captions under them say where each one ends."""
    ordered = sorted(captions, key=lambda c: c.center.x)
    cuts = [picture.x0] + [(a.center.x + b.center.x) / 2 for a, b in zip(ordered, ordered[1:])] + [picture.x1]
    return [(Rect(x0, picture.y0, x1, picture.y1), c) for x0, x1, c in zip(cuts, cuts[1:], ordered)]


def _stacked(clusters: list[tuple[Rect, int]]) -> list[tuple[Rect, int]]:
    """A sign and the tab mounted under it are drawn as separate clusters but are one picture;
    two diagrams one above the other are not, and the height tells them apart."""
    merged = sorted(clusters, key=lambda c: c[0].y0)
    changed = True
    while changed:
        changed = False
        for upper in merged:
            lower = next((c for c in merged if c is not upper and c[0].x0 < upper[0].x1 and c[0].x1 > upper[0].x0
                          and 0 <= c[0].y0 - upper[0].y1 <= TAB_GAP_PT
                          and (c[0] | upper[0]).height <= STACK_MAX_HEIGHT_PT), None)
            if lower is not None:
                merged.remove(upper)
                merged.remove(lower)
                merged.append((upper[0] | lower[0], upper[1] + lower[1]))
                changed = True
                break
    return merged


def _rows(figures: list[tuple[Rect, Entry]]) -> list[list[tuple[Rect, Entry]]]:
    """Pictures whose vertical extents overlap sit in one row and read left to right."""
    rows: list[list[tuple[Rect, Entry]]] = []
    for f in sorted(figures, key=lambda f: f[0].y0):
        if rows and any(_overlap_y(f[0], r) for r, _ in rows[-1]):
            rows[-1].append(f)
        else:
            rows.append([f])
    return [sorted(row, key=lambda f: f[0].x0) for row in rows]


# --- sections --------------------------------------------------------------------


class Section:
    """One HTML page: a chapter, or a front or back matter part of the book."""

    def __init__(self, book: "Book", english_title: str, first_page: int, last_page: int, chapter: int | None):
        self.book = book
        self.root = book.root
        self.english_title = english_title
        self.first_page = first_page
        self.last_page = last_page
        self.chapter = chapter

    @property
    def slug(self) -> str:
        return _slug(self.english_title)

    @property
    def key(self) -> str:
        return f"{self.chapter:02d}" if self.chapter else self.slug

    @property
    def file_name(self) -> str:
        return f"{self.chapter:02d}-{self.slug}.html" if self.chapter else f"{self.slug}.html"

    @property
    def url(self) -> str:
        return SITE_URL + self.file_name

    @cached_property
    def pages(self) -> list[TranslatedPage]:
        return [TranslatedPage(self.root, n, self.english_title, self.book.outline.get(n, {}))
                for n in range(self.first_page, self.last_page + 1)]

    @property
    def title(self) -> str:
        return _text(self.pages[0].title_entry().html)

    @property
    def label(self) -> str:
        return f"Розділ {self.chapter}: {self.title}" if self.chapter else self.title

    @cached_property
    def blocks(self) -> list[Block]:
        return [b for p in self.pages for b in p.blocks()]

    def figures(self) -> list[Figure]:
        out = []
        for b in self.blocks:
            if isinstance(b, Figure):
                out.append(b)
            elif isinstance(b, Aside):
                out.extend(x for x in b.blocks if isinstance(x, Figure))
        return out

    def write(self, out_dir: Path) -> Path:
        image_dir = f"img/{self.key}"
        (out_dir / image_dir).mkdir(parents=True, exist_ok=True)
        for f in self.figures():
            f.crop(self.root / "pages" / f"{f.page:03d}.ua.pdf", out_dir / image_dir / f.image)
        out = out_dir / self.file_name
        out.write_text(self.html(image_dir))
        return out

    def contents(self) -> list[Heading]:
        """The level the section opens with and the one below it, whatever the outline calls them; the
        see-think-do chapter opens one level deeper than the others and closes with a shallower heading."""
        headings = [b for b in self.blocks if isinstance(b, Heading)]
        top = headings[0].level if headings else 0
        return [h for h in headings if h.level <= top + 1]

    def html(self, image_dir: str) -> str:
        top = self.contents()[0].level if self.contents() else 0
        contents = "".join(f'<li class="l{max(0, h.level - top)}"><a href="#{h.id}">{h.text}</a></li>' for h in self.contents())
        description = next((_text(b.html) for b in self.blocks if isinstance(b, Paragraph)), self.title)
        previous, following = self.book.neighbours(self)
        title = html_lib.escape(self.title)
        return PAGE_TEMPLATE.format(
            title=title, label=html_lib.escape(self.label), description=html_lib.escape(description, quote=True),
            url=self.url, site=SITE_URL, schema_type="Chapter" if self.chapter else "Article",
            position=f', "position": {self.chapter}' if self.chapter else "",
            contents=f'<nav class="contents"><ul>{contents}</ul></nav>' if contents else "",
            prev=f'<a class="prev" href="{previous.file_name}">← {html_lib.escape(previous.label)}</a>' if previous else "<span></span>",
            next=f'<a class="next" href="{following.file_name}">{html_lib.escape(following.label)} →</a>' if following else "<span></span>",
            body=render_blocks(self.blocks, image_dir, self.title))


class Book:
    def __init__(self, root: Path):
        self.root = root

    @cached_property
    def toc(self) -> list[tuple[int, str, int]]:
        return pymupdf.open(self.root / "driver-full.pdf").get_toc()

    @cached_property
    def outline(self) -> dict[int, dict[str, int]]:
        """Per page, the outline level of each entry that starts on it, by normalized English title."""
        out: dict[int, dict[str, int]] = {}
        for level, title, page in self.toc:
            out.setdefault(page, {})[_normalized(title)] = level
        return out

    @cached_property
    def sections(self) -> list[Section]:
        starts = [(title, page) for level, title, page in self.toc if level == 1]
        out = []
        for i, (title, page) in enumerate(starts):
            if _normalized(title) in UNPUBLISHED_SECTIONS:
                continue
            m = re.fullmatch(r"Chapter (\d+): (.*)", title.strip())
            english = m.group(2) if m else title.strip()
            out.append(Section(self, english, page, starts[i + 1][1] - 1, int(m.group(1)) if m else None))
        return out

    def chapter(self, number: int) -> Section:
        return next(s for s in self.sections if s.chapter == number)

    def neighbours(self, section: Section) -> tuple[Section | None, Section | None]:
        i = self.sections.index(section)
        return (self.sections[i - 1] if i > 0 else None, self.sections[i + 1] if i + 1 < len(self.sections) else None)

    def write_sitemap(self, out_dir: Path) -> Path:
        urls = [SITE_URL, SITE_URL + "LearnToDriveSmart_UA.pdf", *(s.url for s in self.sections)]
        out = out_dir / "sitemap.xml"
        out.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                       + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n")
        return out


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{label} — Learn to Drive Smart українською</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{url}">
<link rel="icon" href="data:,">
<meta property="og:type" content="article">
<meta property="og:locale" content="uk_UA">
<meta property="og:site_name" content="Learn to Drive Smart українською">
<meta property="og:title" content="{label}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site}cover.jpg">
<script type="application/ld+json">
{{"@context": "https://schema.org", "@type": "{schema_type}", "name": "{title}", "url": "{url}", "inLanguage": "uk",
 "isAccessibleForFree": true{position},
 "isPartOf": {{"@type": "Book", "name": "Learn to Drive Smart українською", "url": "{site}", "inLanguage": "uk"}}}}
</script>
<style>
:root {{ color-scheme: light; }}
body {{ font: 17px/1.55 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #231f20; margin: 0; padding: 0 1rem 4rem; }}
main {{ max-width: 42rem; margin: 0 auto; }}
h1 {{ color: #8387aa; font-weight: 500; font-size: 1.9rem; margin: 2rem 0 1rem; }}
h2 {{ color: #8387aa; font-weight: 600; font-size: 1.5rem; margin: 2.5rem 0 0.5rem; }}
h3 {{ color: #378ac0; font-weight: 600; font-size: 1.2rem; margin: 2rem 0 0.4rem; }}
h4 {{ color: #6a9a2a; font-weight: 600; font-size: 1.05rem; margin: 1.6rem 0 0.3rem; }}
h5 {{ color: #6a9a2a; font-weight: 600; font-size: 1rem; margin: 1.4rem 0 0.3rem; }}
p {{ margin: 0 0 0.9rem; }}
ul {{ margin: 0 0 0.9rem; padding-left: 1.3rem; }}
li {{ margin-bottom: 0.25rem; }}
p.story {{ font-style: italic; }}
p.lead {{ font-weight: 600; font-style: italic; }}
nav.contents {{ background: #f3f3f7; padding: 0.8rem 1.2rem; border-radius: 8px; font-size: 0.95rem; }}
nav.contents ul {{ list-style: none; padding: 0; margin: 0; }}
nav.contents li.l1 {{ margin-left: 1.2rem; }}
nav.contents a {{ color: #378ac0; text-decoration: none; }}
nav.top {{ font-size: 0.9rem; margin-top: 1rem; }}
nav.top a {{ color: #378ac0; }}
aside {{ border-radius: 10px; padding: 0.9rem 1.1rem; margin: 1rem 0 1.2rem; font-size: 0.95rem; }}
aside h4 {{ margin: 0 0 0.5rem; font-size: 1rem; }}
aside p:last-child, aside ul:last-child {{ margin-bottom: 0; }}
aside.note {{ background: #f3f3f7; }}
aside.panel {{ background: #e9e9f2; }} aside.panel h4 {{ color: #231f20; }}
aside.story {{ background: #e9e9f2; }} aside.story h4 {{ color: #231f20; }}
aside.tip {{ background: #eaf3fa; border-left: 5px solid #378ac0; }} aside.tip h4 {{ color: #378ac0; }}
aside.fact {{ background: #fbeaea; border-left: 5px solid #d9413a; }} aside.fact h4 {{ color: #d9413a; }}
aside.warning {{ background: #fbeaea; border-left: 5px solid #d9413a; }} aside.warning h4 {{ color: #d9413a; }}
aside.think {{ background: #eff7e6; border-left: 5px solid #8dc63f; }} aside.think h4 {{ color: #6a9a2a; }}
.gallery {{ display: flex; flex-wrap: wrap; align-items: flex-start; gap: 1.2rem 1rem; margin: 1rem 0 1.5rem; }}
figure {{ margin: 0; flex-grow: 0; flex-shrink: 1; max-width: 100%; font-size: 0.85rem; line-height: 1.35; }}
figure img {{ display: block; max-width: 100%; height: auto; margin-bottom: 0.4rem; border-radius: 4px; }}
figcaption p {{ margin: 0; }}
p.choice {{ align-self: center; flex: 1 1 10rem; font-weight: 600; font-style: italic; margin: 0; font-size: 0.95rem; }}
span.or {{ align-self: center; background: #8387aa; color: #fff; border-radius: 1em; padding: 0.1em 0.7em; font-style: italic; font-weight: 600; }}
span.page {{ display: block; height: 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 1.2rem; font-size: 0.9rem; line-height: 1.4; }}
th {{ background: #8387aa; color: #fff; text-align: left; padding: 0.5rem 0.6rem; font-weight: 600; }}
td {{ border-bottom: 1px solid #ddd; padding: 0.45rem 0.6rem; vertical-align: top; }}
td p, td ul {{ margin: 0; }}
nav.pager {{ display: flex; justify-content: space-between; gap: 1rem; margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #ddd; font-size: 0.95rem; }}
nav.pager a {{ color: #378ac0; text-decoration: none; max-width: 48%; }}
nav.pager a.next {{ text-align: right; margin-left: auto; }}
@media (max-width: 480px) {{ figure {{ flex-basis: calc(50% - 0.5rem) !important; }} p.choice {{ flex-basis: 34%; }} }}
</style>
</head>
<body>
<main>
<nav class="top"><a href="./">Learn to Drive Smart українською</a> › {label}</nav>
<h1>{title}</h1>
{contents}
{body}
<nav class="pager">{prev}{next}</nav>
</main>
<script>
(function () {{
  var key = "reading-position:" + location.pathname;
  var anchors = document.querySelectorAll("[id]");
  function current() {{
    var best = null;
    for (var i = 0; i < anchors.length; i++) {{
      var top = anchors[i].getBoundingClientRect().top;
      if (top <= 80) best = anchors[i]; else break;
    }}
    return best;
  }}
  var pending = null;
  addEventListener("scroll", function () {{
    if (pending) return;
    pending = setTimeout(function () {{
      pending = null;
      var el = current();
      if (el) localStorage.setItem(key, el.id);
    }}, 250);
  }});
  if (!location.hash) {{
    var saved = localStorage.getItem(key);
    var el = saved && document.getElementById(saved);
    if (el) el.scrollIntoView();
  }}
  localStorage.setItem("reading-position:last", location.pathname);
}})();
</script>
</body>
</html>
"""

CAPTION_ROLES = {"body", "sidebar", "caption"}
CAPTION_MAX_PT = 9.0
CAPTION_MIN_WEIGHT = 500
CAPTION_OVERLAP_PT = 4.0
BOX_TEXT_ROLES = {"sidebar", "story", "panel-title"}
BOX_TEXT_MIN_PT = 9.0
BOX_TEXT_MIN_SHARE = 0.12
TITLE_WIDTH_FRACTION = 0.8
BACKGROUND_FRACTION = 0.8
BOX_KINDS = {"driving tip": "tip", "crash fact": "fact", "fast fact": "fact", "warning!": "warning", "think about": "think"}
PARAGRAPH_KINDS = {"story": "story", "caption": "lead"}
SECTION_HEADING_MIN_PT = 16.0
SUBSECTION_HEADING_MIN_PT = 13.0
CELL_TOLERANCE_PT = 2.0
COVER_FRACTION = 0.8
SITE_URL = "https://agayardo.github.io/LearnToDriveSmartBC/"
UNPUBLISHED_SECTIONS = {"learn to drive smart", "statement of limitation", "contents", "index", "back cover: vehicle checklist"}
DROPPED_ROLES = {"running-header", "page-number"}
CONTENTS_LABEL = "in this chapter"
FIGURE_MIN_PT = 20.0
TAB_GAP_PT = 15.0
STACK_MAX_HEIGHT_PT = 120.0
FIGURE_PAD = 2.0
FIGURE_DPI = 192
FIGURE_MIN_PX = 150
PX_PER_PT = 1.4


if __name__ == "__main__":
    book = Book(Path(__file__).resolve().parent.parent)
    docs = book.root / "docs"
    if sys.argv[1:]:
        for number in sys.argv[1:]:
            print(book.chapter(int(number)).write(docs))
    else:
        for section in book.sections:
            print(section.write(docs))
        print(book.write_sitemap(docs))

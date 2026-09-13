# DriveSmartBC — Ukrainian translation

Translate ICBC's driver handbook *Learn to Drive Smart* (British Columbia) into Ukrainian, reproducing the original layout.

## Source

The only input is `driver-full.pdf`. There are no source documents, fonts, or text exports. We reverse engineer the PDF and reassemble it.

## Approach

The book is too large to translate in one pass, and a PDF is not an editable document. The pipeline is:

1. Split `driver-full.pdf` into one file per page.
2. For each page, extract the text layer with positions, translate it into Ukrainian, and lay the translation back into the same positions.
3. Some text is not in the text layer: it is drawn as vector paths inside illustrations (labels on road diagrams, signs). Identify those glyphs, recover the English wording, and repaint the illustration with Ukrainian text.
4. Reassemble the translated pages into a single Ukrainian PDF.

## Per-page translation technique

Remove the English text from the page with redactions that keep drawings and images, lay the Ukrainian text into the same boxes with Avenir Next, and shrink the font where it does not fit. Implemented in `tools/pagekit.py`. The agent procedure is `notes/translate-page.md`.

## Layout

- `driver-full.pdf` — the source.
- `pages/NNN.pdf` — one file per page, produced by `qpdf --split-pages driver-full.pdf pages/%d.pdf`. Never modified.
- `pages/NNN.ua.pdf` — the translated page, written by `apply` from `translations/NNN.json`. A page is done when this file exists. PNG renders in `pages/` are gitignored scratch files.
- `docs/LearnToDriveSmart_UA.pdf` — the translated pages merged in order with `qpdf`, then re-saved with PyMuPDF's full garbage collection so that the Avenir Next faces, which every page embeds, are stored once.
- `docs/` — the GitHub Pages site: `index.html`, the PDF above, its cover, `robots.txt`, `sitemap.xml`, and the HTML edition: one page per chapter and per front or back matter part (`NN-slug.html`, `slug.html`) with its pictures in `docs/img/`. Written for readers of the translation, not for contributors. `index.html` is written by hand; everything else in the HTML edition is written by `tools/sitekit.py`, so edit the translation JSON and regenerate rather than editing those files.
- `translations/NNN.json` — one file per page: region ids mapped to Ukrainian HTML, optional box and centering.
- `translation-report.md` — TODO lines for a human reviewer, appended per page as described in `notes/translate-page.md`.
- `notes/analysis.md` — how the PDF is built and what makes translation hard.
- `notes/translate-page.md` — instructions for the agent that translates one page.
- `translation-glossary-ua.md` — recurring terms whose translation is a choice, `<english text> -> <ua translation>`, read in full before each page and appended when a page settles one. Kept short on purpose.
- `fonts/` — the Avenir Next faces split into `.ttf` files (macOS system fonts, not committed).
- `tools/pagekit.py`, `tests/` — the tool and its tests.
- `tools/sitekit.py` — writes the HTML edition from `translations/*.json` and the region roles `pagekit` derives from the English pages. The layout is not reproduced: headings, paragraphs, and lists flow in reading order; a drawing cluster that is mostly text becomes an aside (driving tip, crash fact, warning, think about, story, strategies panel) placed after the text it sits beside; a cluster that is mostly drawing becomes a picture cropped from `pages/NNN.ua.pdf`, so lettering inside illustrations stays in the picture; rows of captioned pictures become galleries; ruled grids with a white header band become tables. Each page's printed number is an anchor (`#p106`). `.venv/bin/python -m tools.sitekit` writes every page and `docs/sitemap.xml`; a chapter number as argument writes that chapter only.
- `.venv/` — Python with PyMuPDF, fontTools, and pytest.

## Tools

`tools/pagekit.py` holds the deterministic part of the technique above. It needs `.venv` (PyMuPDF, fontTools, pytest) and the faces in `fonts/`.

```bash
.venv/bin/python -m tools.pagekit inspect pages/NNN.pdf          # regions with ids, boxes, styles; places of interest
.venv/bin/python -m tools.pagekit render  pages/NNN.pdf          # pages/NNN.png
.venv/bin/python -m tools.pagekit apply   translations/NNN.json  # pages/NNN.ua.pdf and a preview PNG
.venv/bin/python -m pytest
```

`inspect` groups the text layer into regions (paragraph, heading, sidebar note, caption, bubble, label) in reading order, gives each an id and the box the translation goes into, and lists places of interest: bubbles, pills, narrow captions, small text, illustrations with and without a text layer, tables. Bubble boxes are measured on a render as the widest white rectangle inside the cloud.

`translations/NNN.json` maps region ids to Ukrainian HTML, with an optional box and centering flag per entry. `apply` redacts each region over its full original extent with drawings kept, lays the text into the box with the Avenir Next faces, shrinks until it fits, centres bubble and label text, and reports the scale per box, boxes left untranslated, English words still on the page, and the drawing count before and after. Several regions can share one box.

## Known challenges

- Ukrainian text is longer than English. Body, sidebar, and story text is set at 95% of the original size on every page; boxes that still do not fit shrink further and are flagged for review.
- Every embedded font is a subset with only the glyphs the English text used, and none has Cyrillic glyphs. Avenir Next (see `notes/translate-page.md`) is the substitute.
- Detecting which illustrations contain vectorized text versus pure graphics.
- BC-specific legal and road-sign terminology must be translated the same way on every page; `translation-glossary-ua.md` is the shared record.

## Status

All 177 pages are translated and merged into `docs/LearnToDriveSmart_UA.pdf`. Lettering inside illustrations that is drawn as paths is not handled by the tool.

See [notes/analysis.md](notes/analysis.md) for the PDF inspection results and the proposed pipeline.

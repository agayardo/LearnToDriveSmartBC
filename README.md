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

Proven on printed page 7 with a throwaway script. Documented in `docs/translate-page.md`.

## Layout

- `driver-full.pdf` — the source.
- `pages/NNN.pdf` — one file per page, produced by `qpdf --split-pages driver-full.pdf pages/%d.pdf`. A page is translated in place and renamed to `pages/NNN.ua.pdf`, so a page is done when its `.ua.pdf` exists. Re-run the split command to restore an original. PNG renders in `pages/` are gitignored scratch files.
- `docs/analysis.md` — how the PDF is built and what makes translation hard.
- `docs/translate-page.md` — instructions for the agent that translates one page.
- `docs/glossary.md` — shared terminology.
- `fonts/` — the Avenir Next faces split into `.ttf` files (macOS system fonts, not committed).
- `.venv/` — Python with PyMuPDF and fontTools.

## Tools

`tools/pagekit.py` holds the deterministic part of the technique above. It needs `.venv` (PyMuPDF, fontTools, pytest) and the faces in `fonts/`.

```bash
.venv/bin/python -m tools.pagekit inspect pages/019.pdf   # regions with ids, boxes, styles; places of interest
.venv/bin/python -m tools.pagekit render  pages/019.pdf   # pages/019.png
.venv/bin/python -m translations.019                      # apply one page's translation
.venv/bin/python -m pytest                                 # tests, run against pages/019.pdf
```

`inspect` groups the text layer into regions (paragraph, heading, sidebar note, caption, bubble, label) in reading order, gives each an id and the box the translation goes into, and lists places of interest: bubbles, pills, narrow captions, small text, illustrations with and without a text layer, tables. Bubble boxes are measured on a render as the widest white rectangle inside the cloud.

A page script in `translations/NNN.py` maps region ids to Ukrainian HTML and calls `TranslationJob.save()`. The job redacts each region over its full original extent with drawings kept, lays the text into the box with the Avenir Next faces, shrinks until it fits, centres bubble and label text, and reports the scale per box, boxes left untranslated, English words still on the page, and the drawing count before and after. Several regions can share one box, as the four body paragraphs on page 19 do. `translations/019.py` is the worked example.

## Known challenges

- Ukrainian text is longer than English, so pages need reflow or font-size adjustments.
- Every embedded font is a subset with only the glyphs the English text used, and none has Cyrillic glyphs. Avenir Next (see `docs/translate-page.md`) is the substitute.
- Detecting which illustrations contain vectorized text versus pure graphics.
- BC-specific legal and road-sign terminology needs a glossary so wording stays consistent across pages.

## Status

`tools/pagekit.py` and `translations/019.py` implement the per-page technique; page 19 is translated (`pages/019.ua.pdf`). Lettering inside illustrations that is drawn as paths is not handled yet. The source is split into `pages/`; translation has not started.

See [docs/analysis.md](docs/analysis.md) for the PDF inspection results and the proposed pipeline.

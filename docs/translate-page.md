# Translating one page

Input: `pages/NNN.pdf`. Outputs: `translations/NNN.py` and `pages/NNN.ua.pdf`, which the script writes. Never modify `pages/NNN.pdf`. Follow `translations/019.py`.

```bash
.venv/bin/python -m tools.pagekit render  pages/NNN.pdf   # pages/NNN.png
.venv/bin/python -m tools.pagekit inspect pages/NNN.pdf   # region ids, boxes, places of interest
.venv/bin/python -m translations.NNN                      # pages/NNN.ua.pdf, pages/NNN.ua.png
```

## Regions

Compare the `inspect` output with the render. Lettering that is visible but not listed is vector paths inside the artwork (see below). A paragraph split into several regions, or several paragraphs that should share one box, is one `job.set` call with a list of ids. Pass `rect=Rect(...)` to extend a box into free space; never over artwork or another region.

## Text

HTML: `<p>` per paragraph, `<b>`, `<i>`, list items as `<p class="li">■&nbsp;...`. `&nbsp;` between number and unit. `&#8288;` after "/" in "км/год", or the line breaks there.

- Follow `docs/glossary.md`; add recurring terms you introduce.
- Sign lettering (STOP, YIELD, ONE WAY, speed limits) stays English; translate the captions.
- Keep numbers, units, URLs, phone numbers, "ICBC", "B.C.", form numbers, "Class 5". "GLP" stays, with the Ukrainian expansion in parentheses on first use per page.
- Leave `page-number` untranslated. Translate the running header.
- Bold and italic runs stay on the same words. Formal "ви".
- Do not drop content to make text fit; the box shrinks the font. Bubbles are the exception: tighter wording is fine.

## Report and fix

Body, sidebar, and story text is set at 95% of the original size on every page, so most boxes fit at scale 1.0. The script prints the remaining scale per box. Below 0.9, look at the render and reword or widen the box; a different sentence reads better than 8 pt body text. Pills, captions, and bubbles are short and isolated, so a lower scale there is acceptable. Drawing counts before and after must be equal. "English still on page" must list only kept terms.

## Lettering inside artwork

The tool does not handle it. Sign lettering: leave it. Flat-background labels: after `job.save`, cover the label with a rectangle in the sampled background colour and draw the Ukrainian text with a font from `fonts/`. Rotated, curved, or gradient-background labels: leave them and flag them.

## Done

View `pages/NNN.ua.png` against `pages/NNN.png`. Delete the PNGs.

Anything a person must look at goes into `translation-report.md`, one TODO line per item, appended under a heading with the printed page number. Write for someone looking at the rendered page, not at the tool: say where on the page in words, quote the text, say what to check. No region ids, no coordinates.

```
## Page 7 (Keep learning)
- TODO Left caption under the illustration, "Знайти час, щоб вивчити правила дорожнього руху?": set small to fit next to the "або" pill; check it reads well or shorten it.
- TODO Curved label "Escape route" along the arrow in the diagram: left in English.
```

Flag: boxes still below 0.9 after rewording, lettering left in English other than signs, anything unhandled, and glossary terms you added that may conflict with earlier pages. A clean page adds nothing.

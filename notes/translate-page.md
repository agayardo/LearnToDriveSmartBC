# Translating one page

Input: `pages/NNN.pdf`. Outputs: `translations/NNN.json` and `pages/NNN.ua.pdf`, which `apply` writes. Never modify `pages/NNN.pdf`. The JSON format is documented at the top of `tools/pagekit.py`.

```bash
.venv/bin/python -m tools.pagekit render  pages/NNN.pdf          # pages/NNN.png
.venv/bin/python -m tools.pagekit inspect pages/NNN.pdf          # region ids, boxes, places of interest
.venv/bin/python -m tools.pagekit apply   translations/NNN.json  # pages/NNN.ua.pdf, pages/NNN.ua.png
```

## Regions

Compare the `inspect` output with the render. Lettering that is visible but not listed is vector paths inside the artwork (see below). Each entry in `regions` has `ids` and `html`. Several ids in one entry share one box: a paragraph the tool split, or paragraphs that should flow together. Add `rect` to extend a box into free space; never over artwork or another region. Add `center` for text that sits in a shape.

## Text

HTML: `<p>` per paragraph, `<b>`, `<i>`, list items as `<p class="li">■&nbsp;...`. `&nbsp;` between number and unit. `&#8288;` after "/" in "км/год", or the line breaks there.

- Before translating, read `translation-glossary-ua.md` (if it exists) and use its translations. Append a line `<english text> -> <ua translation>` for a term that might recur on other pages and where another translator could plausibly choose a different translation; create the file if it does not exist. Where the English alone is ambiguous, add the minimum context in parentheses to say what is being translated, e.g. `or (pill between two choices) -> або`. Not one-off sentences, not terms with one obvious translation. The file is read in full on every page; keep it short.
- Sign lettering (STOP, YIELD, ONE WAY, speed limits) stays English; translate the captions.
- Keep numbers, units, URLs, phone numbers, "ICBC", "B.C.", form numbers, "Class 5". "GLP" stays, with the Ukrainian expansion in parentheses on first use per page.
- Leave `page-number` untranslated. Translate the running header.
- Bold and italic runs stay on the same words. Formal "ви".
- Do not drop content to make text fit; the box shrinks the font. Bubbles are the exception: tighter wording is fine.

## Report and fix

Body, sidebar, and story text is set at 95% of the original size on every page, so most boxes fit at scale 1.0. The script prints the remaining scale per box. Below 0.9, look at the render and reword or widen the box; a different sentence reads better than 8 pt body text. Pills, captions, and bubbles are short and isolated, so a lower scale there is acceptable. Drawing counts before and after must be equal. "English still on page" must list only kept terms. Fix by editing the JSON and re-running `apply`.

## Lettering inside artwork

The tool does not handle it. Sign lettering: leave it. Flat-background labels: after `apply`, cover the label with a rectangle in the sampled background colour and draw the Ukrainian text with a font from `fonts/`. Rotated, curved, or gradient-background labels that carry information: leave them and add a TODO. Decorative lettering that carries none (a book cover, a brand name on a vehicle): leave it, no TODO.

## Done

View `pages/NNN.ua.png` against `pages/NNN.png`. Delete the PNGs.

A TODO in `translation-report.md` records a defect you left on the page. All three must hold: the page is wrong or incomplete at that spot; you tried and could not fix it within these rules (meaning would be lost, no space, label cannot be repainted); a person has to act. Not observations, not "check this reads well", not anything these instructions told you to leave as is. Most pages add nothing.

Append under a heading with the printed page number; create the file if it does not exist, with the single line `# Translation report` at the top. Write for someone looking at the rendered page: where in words, the quoted text, what is wrong. No region ids, no coordinates.

```
## Page NN (section title)
- TODO <where on the page>, "<quoted text>": <what is wrong and why it could not be fixed>.
```

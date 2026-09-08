# PDF analysis

Findings from inspecting `driver-full.pdf` with PyMuPDF and qpdf. Nothing here is implemented yet.

## The file

| Property | Value |
|---|---|
| Pages | 177, all 504 x 720 pt (7 x 10 in) |
| Producer | Adobe InDesign CC 2015, Adobe PDF Library 15.0 |
| Created / modified | 2016-01-20 / 2026-04-08 |
| Encryption | AES-128, empty user password, permissions restricted (P = -1036) |
| Tagged PDF | No. No structure tree, so no reading order metadata. |
| Bookmarks | 338 outline entries, two levels (chapter, section) |
| Page labels | Present (A, B, i, 1, 2, ... , D) |
| Links, annotations, form fields | None. The AcroForm dictionary is empty. |
| Raster images | 12 images on 10 pages (cover photo, a licence card, a few photos). |
| Text volume | 51,087 words, 328,655 characters |

The empty user password means the file opens without a password. The permission flags only ask viewers to refuse copying and editing. PyMuPDF and qpdf ignore them, so the restrictions do not block the pipeline.

Chapters (PDF page numbers): front matter 1-16, chapters 1-10 on 17-168, index 169-172, test information and ID tables 173-176, back cover 177.

## Page anatomy

Every page follows the same construction:

- One full-page Form XObject (`/Fm0`) drawn first. It contains all artwork: road diagrams, signs, vehicles, sidebar boxes, table rules. It contains no text operators on any page.
- The page content stream then draws all text with `Tj`/`TJ` operators on top of the artwork.

This separation is the main reason the project is feasible. Removing every `BT ... ET` block from the page content streams leaves the artwork untouched, and Ukrainian text can be drawn into the same rectangles. A throwaway spike confirmed this on page 85: the body text disappeared, the diagram and sidebar boxes stayed, and Cyrillic text rendered with a system font.

Caveats found by the spike:

- 18 pages have more than one content stream (InDesign splits streams at about 150 KB). Text can appear in any of them, so strip all streams, not the first.
- Body text uses `TJ` arrays with per-glyph kerning. Position information is in the text layer, so extraction with word and span coordinates is reliable.

## Text layer

Fonts are all subsetted, so none has Cyrillic glyphs. There are 110 distinct font and size combinations, but a few dominate:

| Role | Font | Size |
|---|---|---|
| Body text | Avenir Book | 9.5 pt, leading 1.211 |
| Sidebar text | Avenir Light | 7.5 pt |
| Bold inline terms | Avenir Heavy | 9.5 pt |
| Section headings | Avenir Heavy | 11.5 pt |
| Sidebar titles ("driving tip", "warning!") | Avenir Medium | 13-14 pt |
| Running header, page number | Gotham Book / Medium | 12 / 9 pt |
| Chapter titles | Gotham Book/Medium | 14-17 pt |

Thirteen pages use `AvenirLTStd-*` instead of `Avenir-*`. They render identically. They are pages edited later in a different InDesign environment.

Extracted text needs normalization before translation:

- Ligatures `ﬁ` and `ﬂ` (23 occurrences), curly quotes, en and em dashes.
- Soft hyphens, non-breaking hyphens, thin spaces, narrow no-break spaces, zero-width spaces.
- Tab characters (834) and `\x07` (40) from InDesign "indent to here" markers in bullet lists.
- Only 20 lines end with a hyphen, so hyphenation is rare and can be handled manually.

Reading order must be inferred from geometry. The layout is regular: a running header at the top, a page number at the bottom outer corner, a narrow sidebar column (x 67-156 pt) and a main column (x 180-450 pt, or x 313-450 pt beside an illustration).

## Vectorized text

This is the hard part. All lettering inside illustrations is drawn as filled paths inside `/Fm0`. Confirmed by overlaying text-layer word boxes on renders:

- Diagram labels. Page 85's stopping-distance diagram has eight labels and a title, all paths. Page 144's Graduated Licensing Program diagram is mostly paths, with a few lines of real text added over the top in a later edit.
- Sign lettering. STOP, YIELD, ONE WAY, "30 km/h", "PREPARE TO STOP", "3 TRACKS", construction-zone signs.
- Vehicle markings. DOWNTOWN on a bus, POLICE, AMBULANCE, speedometer numerals.
- Text along a path. The "Escape route" label on page 85 follows a curved arrow.

Counting pages by artwork density: 68 pages have almost no artwork, 51 have light artwork, 58 have 200 or more paths. Vectorized text appears on a subset of the 109 artwork pages. A heuristic on small filled paths flags 95 pages but overcounts, because road dashes and vehicle details look glyph-sized. Reliable detection needs a visual pass (render each page and inspect it) rather than a geometric rule.

Repainting strategy options, in order of effort:

1. Cover the English glyph paths with a filled rectangle in the background colour and draw Ukrainian text on top. Works for labels on flat backgrounds (most diagram labels). Fails where the background is a gradient or the text is rotated.
2. Locate and delete the glyph paths from the XObject content stream, then draw Ukrainian text. Cleaner, needs path clustering to identify glyph groups.
3. Redraw the illustration element. Only needed for text on curves or on complex backgrounds.

Policy decision needed: sign lettering (STOP, YIELD, speed limits) is what a driver sees on BC roads. Recommendation: keep sign wording in English and translate only the captions, as the signs themselves are not translated in BC. Diagram labels and vehicle markings should be translated.

## Special pages

- Page 15 shows two miniature pages (46 and 69) as real text at about 2.8 pt with a "Sidebar" and "Main column" callout. Translating it means generating thumbnails of the translated pages 46 and 69.
- Pages 5-12 are the table of contents with dot leaders and page numbers. Pages 169-172 are the index. Both refer to printed page numbers. If pagination stays 1:1 with the original, the numbers stay valid. The index must be re-sorted by the Ukrainian alphabet.
- Pages 2, 158, 176 are dense tables (checklist, licence classes, ID documents). Table cells are artwork rules with text on top, so cell heights are fixed and Ukrainian text must fit them.
- Page 1 (cover) and 177 (back cover) use different fonts (Tondo, Graphik, Nunito) and have the only large raster image.

## Layout expansion

Ukrainian runs about 10-20% longer than English in characters, and Cyrillic glyphs are wider on average. At the original 9.5 pt, body paragraphs will not fit their boxes. Options:

- Reduce font size per box until the text fits (PyMuPDF's `fill_textbox` reports overflow, so this can be automatic). Body 9.5 pt to about 8.5 pt and sidebar 7.5 pt to about 7 pt is likely enough for most pages.
- Where a whole column overflows, shift following blocks down within the free space on the page.
- Keep pagination 1:1 with the original so the table of contents, index, and cross-references ("see chapter 5") stay correct.

Translation must also handle inline bold and italic runs inside paragraphs, since the text layer marks them as separate spans with different fonts.

## Fonts for the Ukrainian output

The macOS system font Avenir Next has full Cyrillic coverage including the Ukrainian letters Є, І, Ї, Ґ, and looks close to Avenir. Helvetica Neue also covers Cyrillic. Both are licensed for use on the machine, not for embedding in a redistributed PDF. For a distributable result, use open fonts with Cyrillic: Montserrat (close to Gotham) and Nunito Sans or Mulish (close to Avenir). The choice needs a decision on how the result will be distributed.

## Tooling

PyMuPDF handled everything needed: content stream access, text extraction with coordinates, path enumeration, text insertion with an external font, rendering. qpdf is available for stream inspection. No other PDF tools are installed.

## Proposed pipeline

1. Split into 177 single-page PDFs.
2. For each page, extract text blocks with coordinates and styles into a JSON file. Normalize characters. Group spans into paragraphs.
3. Translate each page's JSON, preserving block ids and inline style runs. Maintain a glossary for recurring terms (driving tip, warning!, see-think-do, Class 5, GLP, N and L signs).
4. Strip all text operators from all content streams of the page. Draw the translated blocks into the original rectangles with fitting.
5. For artwork pages, render before and after, review visually, and repaint vectorized labels from a per-page list of label replacements.
6. Regenerate the table of contents and index text from the translated pages. Merge pages, restore bookmarks and page labels.

## Non-technical

The handbook is ICBC copyrighted content. Distributing a translation needs ICBC's permission. Confirm this before anything is published.

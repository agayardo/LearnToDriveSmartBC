import re
from pathlib import Path

import pymupdf
import pytest

from tools.pagekit import Page, TranslationJob

ROOT = Path(__file__).resolve().parent.parent
PAGE_19 = ROOT / "pages" / "019.pdf"
PAGE_14 = ROOT / "pages" / "014.pdf"


@pytest.fixture(scope="module")
def page19() -> Page:
    return Page(PAGE_19)


def region_by_text(page: Page, needle: str):
    matches = [r for r in page.regions if needle in r.english]
    assert len(matches) == 1, [r.english for r in matches]
    return matches[0]


def test_page_19_heading_keep_learning_is_a_heading_region_in_the_main_column(page19):
    heading = region_by_text(page19, "Keep learning")
    assert heading.role == "heading"
    assert heading.style.size == 14.0
    assert heading.style.color == "#378ac0"
    assert heading.style.weight == 600
    assert (round(heading.rect.x0), round(heading.rect.y0)) == (180, 69)


def test_page_19_running_header_and_page_number_are_separate_roles(page19):
    assert region_by_text(page19, "chapter 1 — you in the driver’s seat").role == "running-header"
    number = [r for r in page19.regions if r.role == "page-number"]
    assert [r.english for r in number] == ["7"]


def test_page_19_four_body_paragraphs_each_become_one_region_with_inline_bold(page19):
    bodies = [r for r in page19.regions if r.role == "body"]
    assert len(bodies) == 4
    assert bodies[0].english.startswith("You’re reading this guide")
    assert bodies[3].html.endswith("(see <b>chapter 9 — your licence</b>).</p>")


def test_a_list_item_opening_with_a_bold_run_is_a_regular_weight_region_with_that_run_bold():
    item = region_by_text(Page(PAGE_14), "presents some of the")
    assert item.style.weight == 400
    assert item.html == (
        '<p class="li">■&nbsp;<b>Chapter 1, you in the driver’s seat</b>, '
        "presents some of the common choices that every driver makes.</p>"
    )


def test_page_19_story_panel_text_is_italic_and_the_question_is_bold_italic(page19):
    story = region_by_text(page19, "you spot a playground sign")
    assert story.style.italic is True
    assert story.role == "story"
    question = region_by_text(page19, "What choice would you make next time?")
    assert question.style.italic is True and question.style.weight == 600


def test_page_19_thought_bubbles_are_bubble_regions_with_rect_inside_the_white_shape(page19):
    bubbles = [r for r in page19.regions if r.role == "bubble"]
    assert [b.english for b in bubbles] == [
        "Playground zones: 30 km/h limit is in effect every day from dawn to dusk.",
        "Signs are easy. I’ll know what they mean when I see them.",
    ]
    left, right = bubbles
    # the left cloud's white fill spans x 195-286, y 218-286; the usable box is the widest text-shaped
    # white rectangle inside it, measured on a render, which stays clear of the cloud bumps
    assert [round(v, 1) for v in left.rect] == [207.2, 237.5, 266.0, 264.5]
    assert [round(v, 1) for v in right.rect] == [336.5, 237.5, 395.0, 264.5]
    assert left.style.size == pytest.approx(6.2, abs=0.1)
    assert left.center is True


def test_page_19_or_pill_is_a_label_region_centred_on_the_pill(page19):
    pill = [r for r in page19.regions if r.english == "or"][0]
    assert pill.role == "label"
    assert pill.style.color == "#ffffff"
    assert pill.rect.width > 20  # the pill shape, not the two-letter word


def test_page_19_side_by_side_captions_are_two_regions_left_then_right(page19):
    left = region_by_text(page19, "Take the time to learn the rules of the road?")
    right = region_by_text(page19, "Not worry about it?")
    assert left.rect.x1 < right.rect.x0
    assert left.role == right.role == "caption"


def test_page_19_places_of_interest_name_bubbles_pill_and_the_illustration(page19):
    notes = "\n".join(page19.places_of_interest())
    assert "bubble" in notes
    assert "label" in notes
    assert "illustration" in notes


def test_translating_every_region_of_page_19_leaves_no_english_and_keeps_all_drawings(tmp_path):
    job = TranslationJob(PAGE_19)
    for r in job.page.regions:
        if r.role == "page-number":
            continue
        job.set(r.id, "<p>Текст</p>")
    out = tmp_path / "019.ua.pdf"
    report = job.save(out)

    result = pymupdf.open(out)[0]
    assert re.findall(r"[A-Za-z]{2,}", result.get_text()) == []
    assert result.get_text().count("Текст") == len(job.page.regions) - 1
    assert len(result.get_drawings()) == len(pymupdf.open(PAGE_19)[0].get_drawings())
    assert any("Avenir Next" in f[3] for f in result.get_fonts())
    assert report.untranslated == ["7"]


def test_merged_body_regions_share_one_box_and_report_their_scale(tmp_path):
    job = TranslationJob(PAGE_19)
    bodies = [r.id for r in job.page.regions if r.role == "body"]
    long_text = "<p>" + "Дуже довгий абзац українською мовою. " * 40 + "</p>"
    job.set(bodies, long_text)
    report = job.save(tmp_path / "019.ua.pdf")

    placed = report.placements["+".join(bodies)]
    assert placed.scale < 0.9
    assert placed.rect.y0 == pytest.approx(407, abs=1)
    assert placed.rect.y1 == pytest.approx(647, abs=1)
    assert "+".join(bodies) in "\n".join(report.tight())


def test_region_translated_into_a_custom_rect_is_redacted_over_its_original_extent(tmp_path):
    job = TranslationJob(PAGE_19)
    bubble = [r for r in job.page.regions if r.role == "bubble"][0]
    narrow = pymupdf.Rect(bubble.rect.x0 + 20, bubble.rect.y0, bubble.rect.x1 - 20, bubble.rect.y1)
    job.set(bubble.id, "<p>Так</p>", rect=narrow)
    for r in job.page.regions:
        if r.id != bubble.id and r.role != "page-number":
            job.set(r.id, "<p>Текст</p>")
    job.save(tmp_path / "019.ua.pdf")

    assert re.findall(r"[A-Za-z]{2,}", pymupdf.open(tmp_path / "019.ua.pdf")[0].get_text()) == []


def test_cli_inspect_prints_region_ids_and_places_of_interest(capsys):
    from tools.pagekit import main

    main(["inspect", str(PAGE_19)])
    out = capsys.readouterr().out
    assert "r01" in out
    assert "Keep learning" in out
    assert "Places of interest" in out


def test_body_and_sidebar_text_is_set_at_95_percent_and_headings_at_full_size(page19):
    body = [r for r in page19.regions if r.role == "body"][0]
    assert body.style.size == 9.5
    assert "font-size: 9.0pt" in body.css()
    heading = region_by_text(page19, "Keep learning")
    assert "font-size: 14.0pt" in heading.css()


def test_apply_reads_a_json_translation_file_and_writes_the_ua_pdf(tmp_path):
    import json
    from tools.pagekit import main

    spec = {
        "page": "pages/019.pdf",
        "regions": [
            {"ids": ["r02"], "html": "<p>Продовжуйте вчитися</p>"},
            {"ids": ["r11", "r12", "r13", "r14"], "html": "<p>Текст</p>", "rect": [180, 407, 450, 660]},
            {"ids": ["r09"], "html": "<p>або</p>", "center": True},
        ],
    }
    spec_path = tmp_path / "019.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "019.ua.pdf"

    main(["apply", str(spec_path), "--out", str(out)])

    text = pymupdf.open(out)[0].get_text()
    assert "Продовжуйте вчитися" in text and "Keep learning" not in text
    assert "You’re reading this guide" not in text
    assert "As you’re driving" in text  # untranslated regions stay English


def test_the_committed_page_19_translation_applies_cleanly(tmp_path):
    from tools.pagekit import main

    out = tmp_path / "019.ua.pdf"
    main(["apply", str(ROOT / "translations" / "019.json"), "--out", str(out)])
    page = pymupdf.open(out)[0]
    assert re.findall(r"[A-Za-z]{2,}", page.get_text()) == []
    assert "Продовжуйте вчитися" in page.get_text()

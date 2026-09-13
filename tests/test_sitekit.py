from pathlib import Path

import pytest

from tools.sitekit import Book, Figure, Heading, PageStart, Paragraph

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def chapter3():
    return Book(ROOT).chapter(3)


def test_chapter_3_covers_pages_40_to_51_and_is_titled_from_the_translated_chapter_bar(chapter3):
    assert (chapter3.first_page, chapter3.last_page) == (40, 51)
    assert chapter3.slug == "signs-signals-and-road-markings"
    assert chapter3.title == "знаки, сигнали та дорожня розмітка"


def test_chapter_3_sections_are_signs_signals_and_road_markings_with_subsections_one_level_below(chapter3):
    headings = [b for b in chapter3.blocks if isinstance(b, Heading)]
    assert [h.text for h in headings if h.level == 2] == ["Знаки", "Сигнали", "Дорожня розмітка"]
    assert [h.id for h in headings if h.level == 3][:4] == [
        "regulatory-signs", "school-playground-and-crosswalk-signs", "lane-use-signs", "turn-control-signs"]


def test_chapter_3_has_153_sign_figures_each_with_its_caption(chapter3):
    figures = [b for b in chapter3.blocks if isinstance(b, Figure)]
    assert len(figures) == 153
    assert all(f.caption for f in figures)


def test_regulatory_signs_gallery_reads_row_by_row_left_to_right(chapter3):
    blocks = chapter3.blocks
    heading = next(i for i, b in enumerate(blocks) if isinstance(b, Heading) and b.id == "regulatory-signs")
    assert isinstance(blocks[heading + 1], Paragraph)
    assert blocks[heading + 1].html.startswith("<p>Ці знаки повідомляють вам про закони")
    first_row = [b.caption for b in blocks[heading + 2:heading + 6]]
    assert first_row == [
        "Повна зупинка — рухайтеся далі лише тоді, коли це безпечно",
        "Уступіть право переваги іншим транспортним засобам і пішоходам, які переходять дорогу",
        "Максимальна дозволена швидкість, коли дорога чиста й суха, а видимість добра.",
        "Показує нижче обмеження швидкості попереду",
    ]
    second_row_first = blocks[heading + 6]
    assert second_row_first.caption.startswith("Не виїжджайте на цю дорогу")


def test_a_school_zone_sign_and_its_speed_tab_are_one_figure(chapter3):
    figure = next(b for b in chapter3.blocks if isinstance(b, Figure) and b.caption.startswith("Шкільна зона — обмеження 50"))
    assert figure.page == 42
    assert figure.rect.y0 < 255 and figure.rect.y1 > 325


def test_the_in_this_chapter_box_running_headers_and_page_numbers_are_not_part_of_the_chapter_text(chapter3):
    text = " ".join(b.html for b in chapter3.blocks if isinstance(b, Paragraph))
    assert "у цьому розділі" not in text
    assert "розвиток навичок розумного водіння" not in text
    assert "<p>29</p>" not in text


def test_chapter_page_is_written_with_cropped_sign_images_and_printed_page_anchors(chapter3, tmp_path):
    out = chapter3.write(tmp_path)
    assert out == tmp_path / "03-signs-signals-and-road-markings.html"
    html = out.read_text()
    assert '<h1>знаки, сигнали та дорожня розмітка</h1>' in html
    assert '<span id="p30" class="page"></span>' in html
    assert '<h3 id="regulatory-signs">Регулювальні знаки</h3>' in html
    first_sign = 'src="img/03/041-01.png"'
    assert first_sign in html
    assert (tmp_path / "img/03/041-01.png").stat().st_size > 1000


# --- chapters with sidebars, panels, stories, and "or" pills ------------------------


from tools.sitekit import Aside, Pill  # noqa: E402


@pytest.fixture(scope="module")
def chapter5():
    return Book(ROOT).chapter(5)


@pytest.fixture(scope="module")
def chapter1():
    return Book(ROOT).chapter(1)


def asides(chapter, kind):
    return [b for b in chapter.blocks if isinstance(b, Aside) and b.kind == kind]


def test_chapter_5_driving_tip_about_backing_up_follows_the_backing_up_paragraph(chapter5):
    blocks = chapter5.blocks
    tip = next(b for b in asides(chapter5, "tip") if "звуковим сигналом" in b.blocks[0].html)
    assert tip.title == "порада щодо водіння"
    before = blocks[blocks.index(tip) - 1]
    assert isinstance(before, Paragraph) and before.html.startswith("<p><b>Задній хід</b>")


def test_chapter_5_strategies_panel_holds_its_title_and_a_four_item_list(chapter5):
    panel = next(b for b in asides(chapter5, "panel") if b.title == "Стратегії: виконання маневру")
    assert panel.blocks[0].html.startswith("<p>Перевіряйте дзеркала")
    assert panel.blocks[0].html.count("<li>") == 4
    assert panel.blocks[0].html.endswith("<li>повернути ліворуч або праворуч.</li></ul>")


def test_chapter_5_crash_fact_on_intersections_keeps_its_source_line(chapter5):
    fact = next(b for b in asides(chapter5, "fact") if "60 відсотків" in b.blocks[0].html)
    assert fact.title == "факт про аварії"
    assert [b.html for b in fact.blocks][1].startswith("<p>Джерело: середнє за п’ять років")


def test_chapter_5_vision_blocks_list_is_one_list_and_its_two_pictures_have_no_caption(chapter5):
    blocks = chapter5.blocks
    heading = next(i for i, b in enumerate(blocks) if isinstance(b, Heading) and b.id == "vision-blocks")
    assert blocks[heading + 2].html.count("<li>") == 4
    assert blocks[heading + 2].html.startswith("<ul><li>автобус, який закриває вам огляд")
    pictures = [b for b in blocks[heading:heading + 12] if isinstance(b, Figure)]
    assert [(p.page, p.caption) for p in pictures] == [(76, ""), (76, "")]


def test_chapter_5_lettering_inside_pictures_is_not_repeated_as_text(chapter5):
    text = " ".join(b.html for b in chapter5.blocks if isinstance(b, Paragraph))
    assert "Сліпа зона" not in text
    assert "<p>?</p>" not in text


def test_chapter_5_you_in_the_drivers_seat_story_ends_with_its_question(chapter5):
    story = next(b for b in asides(chapter5, "story") if "перед знаком STOP" in b.blocks[0].html)
    assert story.title == "Ви за кермом"
    assert [b.kind for b in story.blocks] == ["story", "story"]
    assert story.blocks[1].html == "<p>Що б ви зробили?</p>"


def test_chapter_1_choice_panel_shows_two_pictures_with_an_or_pill_between_them(chapter1):
    assert (chapter1.first_page, chapter1.last_page, chapter1.slug) == (17, 24, "you-in-the-driver-s-seat")
    panel = next(b for b in asides(chapter1, "story") if b.title == "Ви за кермом – частина 2")
    kinds = [type(b).__name__ for b in panel.blocks]
    assert kinds == ["Paragraph", "Paragraph", "Figure", "Pill", "Figure"]
    assert panel.blocks[1].html == "<p>Який вибір ви зробите?</p>"
    assert [panel.blocks[2].caption, panel.blocks[3].text, panel.blocks[4].caption] == [
        "Зосередитися на водінні?", "чи", "Зосередитися на сварці?"]


def test_chapter_1_page_is_written_with_asides_and_nested_gallery(chapter1, tmp_path):
    html = chapter1.write(tmp_path).read_text()
    assert '<aside class="story"><h4>Ви за кермом – частина 2</h4>' in html
    assert '<aside class="think"><h4>подумайте</h4>' in html
    assert '<span class="or">чи</span>' in html


# --- tables ------------------------------------------------------------------------


from tools.sitekit import Table  # noqa: E402


@pytest.fixture(scope="module")
def chapter2():
    return Book(ROOT).chapter(2)


@pytest.fixture(scope="module")
def chapter7():
    return Book(ROOT).chapter(7)


@pytest.fixture(scope="module")
def chapter9():
    return Book(ROOT).chapter(9)


def tables(chapter):
    return [b for b in chapter.blocks if isinstance(b, Table)]


def test_gear_table_has_three_headers_and_the_reverse_row_fills_both_transmission_columns(chapter2):
    gears = tables(chapter2)[0]
    assert [c.text for c in gears.header] == ["Передача", "Автоматична*", "Механічна*"]
    assert [c.text for c in gears.rows[0]] == ["P – Park (стоянка)", "Для запуску транспортного засобу та для стоянки. Блокує коробку передач.", ""]
    assert [c.text for c in gears.rows[1]] == [
        "R – Reverse (задній хід)",
        "Для руху назад. Вмикає ліхтарі заднього ходу (білі).",
        "Для руху назад. Вмикає ліхтарі заднього ходу (білі).",
    ]
    footnote = chapter2.blocks[chapter2.blocks.index(gears) + 1]
    assert footnote.html == "<p>* Наведені швидкості приблизні й залежать від вашого транспортного засобу.</p>"


def test_alcohol_effects_table_splits_its_merged_header_and_spans_the_see_label_over_five_rows(chapter7):
    effects = next(t for t in tables(chapter7) if t.header[0].text == "Здатність")
    assert [c.text for c in effects.header] == ["Здатність", "Симптоми водія", "Вплив на водія"]
    see, symptoms, effect = effects.rows[0]
    assert (see.text, see.rowspan) == ("Дивись", 5)
    assert symptoms.html == "<ul><li>схильність дивитися в одну точку</li></ul>"
    assert len(effects.rows[1]) == 2


def test_fines_table_ends_with_the_total_row(chapter9):
    fines = next(t for t in tables(chapter9) if t.header[0].text == "Правопорушення")
    assert [c.text for c in fines.header] == ["Правопорушення", "Штраф*", "Бали"]
    assert [c.text for c in fines.rows[0]] == ["Перевищення швидкості на 1–20 км у шкільній зоні", "$196", "3"]
    assert [c.text for c in fines.rows[-1]] == ["Разом", "$1254", "21"]


def test_table_renders_with_header_cells_and_rowspan(chapter7, tmp_path):
    html = chapter7.write(tmp_path).read_text()
    assert "<table><thead><tr><th>Здатність</th><th>Симптоми водія</th><th>Вплив на водія</th></tr></thead>" in html
    assert '<td rowspan="5">Дивись</td>' in html


# --- the whole site ----------------------------------------------------------------


def test_the_site_has_sixteen_pages_in_book_order_with_neighbours_linked():
    book = Book(ROOT)
    names = [s.file_name for s in book.sections]
    assert names[:3] == ["what-to-take-to-the-driver-licensing-office.html", "using-this-guide.html", "01-you-in-the-driver-s-seat.html"]
    assert names[-2:] == ["examiners-tips-for-passing-the-class-5-and-7-road-tests.html", "identification-id.html"]
    assert len(names) == 16
    previous, following = book.neighbours(book.chapter(10))
    assert (previous.file_name, following.file_name) == ("09-your-licence.html", "about-the-knowledge-test.html")


def test_sitemap_lists_the_index_the_pdf_and_every_page(tmp_path):
    text = Book(ROOT).write_sitemap(tmp_path).read_text()
    assert text.count("<loc>") == 18
    assert "<loc>https://agayardo.github.io/LearnToDriveSmartBC/09-your-licence.html</loc>" in text


def test_glp_diagram_with_its_labels_is_one_picture_not_a_note(chapter9):
    blocks = chapter9.blocks
    start = blocks.index(next(b for b in blocks if isinstance(b, PageStart) and b.label == "136"))
    page = blocks[start + 1:start + 5]
    assert [type(b).__name__ for b in page] == ["Heading", "Paragraph", "Figure", "PageStart"]
    assert (round(page[2].rect.y0), round(page[2].rect.y1)) == (169, 615)
    assert "<p>Нуль алкоголю в крові</p>" not in [b.html for b in blocks if isinstance(b, Paragraph)]


# --- heading levels follow the book's outline -------------------------------------------


def test_chapter_5_headings_nest_as_the_outline_does_and_its_contents_list_the_top_two_levels(chapter5):
    headings = {h.text: h.level for h in chapter5.blocks if isinstance(h, Heading)}
    assert headings["Спостереження"] == 3
    assert headings["Спостереження назад"] == 4
    assert headings["Перешкоди для огляду"] == 5
    contents = chapter5.contents()
    assert [h.text for h in contents][:3] == ["Спостереження", "Спостереження вперед", "Спостереження назад"]
    assert contents[-1].text == "Застосування «дивись – думай – дій»"
    assert all(h.level <= 4 for h in contents)
    assert "Перешкоди для огляду" not in [h.text for h in contents]


def test_a_heading_missing_from_the_outline_takes_its_level_from_its_size():
    booking = next(h for h in Book(ROOT).chapter(10).blocks if isinstance(h, Heading) and h.id == "booking-road-tests-and-licensing-information")
    assert booking.level == 2

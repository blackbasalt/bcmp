"""Parsing the SVG of a floor plan into contours — the only seam below HTTP.

It exists because the interesting cases here are broken and hostile files: without a
`viewBox`, with the `id` of a space that does not exist, with a repeated `id`, with no
paths at all. They can be expressed by uploading a file through the form, but then the
screen's test set turns into a factory of file stubs, and the reason for a rejection is
read through a message on the page instead of the reason itself.

What is checked is what the parse makes observable: what became a contour, what was left
unmatched and what the file is rejected on. The rendering of the contours themselves is
checked through the floor screen.
"""

import pytest

from building_passport.floor_plan_svg import PlanUnreadable, read_plan

# A real plan is mostly drawing: walls, hatching, captions. Only a path with an `id`
# becomes a contour, so the samples carry both.
WALL = '<path d="M0 0 L100 0" />'


def svg(body, view_box='0 0 100 100', **root):
    attrs = "".join(f' {name}="{value}"' for name, value in root.items())
    box = f' viewBox="{view_box}"' if view_box is not None else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg"{box}{attrs}>{body}</svg>'


def contour(code, d="M0 0 L10 0 L10 10 Z"):
    return f'<path id="{code}" d="{d}" />'


# What becomes a contour


def test_a_valid_file_yields_one_contour_per_matched_path():
    """A parsed plan is the spaces, drawn; there is nothing extra in it."""
    reading = read_plan(svg(contour("man-f1-a") + contour("man-f1-b")), ["man-f1-a", "man-f1-b"])

    assert {c.code for c in reading.contours} == {"man-f1-a", "man-f1-b"}


def test_the_geometry_of_a_contour_is_kept_as_it_was_drawn():
    """A contour is the geometry from the file, not a recomputation of it."""
    reading = read_plan(svg(contour("man-f1-a", d="M1 2 L3 4 Z")), ["man-f1-a"])

    assert reading.contours[0].path_d == "M1 2 L3 4 Z"


def test_the_drawing_itself_does_not_become_contours():
    """Walls and hatching carry no `id` — a contour is put there by a space, not by a line."""
    reading = read_plan(svg(WALL + contour("man-f1-a")), ["man-f1-a"])

    assert len(reading.contours) == 1
    assert reading.unmatched == ()


def test_a_contour_drawn_inside_a_group_is_found():
    """SVG editors lay a drawing out in layers; the nesting is their business, not ours."""
    reading = read_plan(svg(f"<g><g>{contour('man-f1-a')}</g></g>"), ["man-f1-a"])

    assert [c.code for c in reading.contours] == ["man-f1-a"]


def test_a_file_without_a_namespace_is_read_all_the_same():
    """An export without `xmlns` is commonplace, and that does not stop the file being a plan."""
    body = contour("man-f1-a")

    reading = read_plan(f'<svg viewBox="0 0 100 100">{body}</svg>', ["man-f1-a"])

    assert [c.code for c in reading.contours] == ["man-f1-a"]


def test_bytes_are_read_the_same_as_text():
    """The file arrives as bytes: the parse must not depend on who decoded them."""
    reading = read_plan(svg(contour("man-f1-a")).encode(), ["man-f1-a"])

    assert [c.code for c in reading.contours] == ["man-f1-a"]


# Incomplete data — a plan loads against it, not after it


def test_a_path_matching_no_space_is_reported_rather_than_dropped():
    """A typo in an `id` must be visible: a silently lost path is a lost space."""
    reading = read_plan(svg(contour("man-f1-a") + contour("man-f1-zz")), ["man-f1-a"])

    assert reading.unmatched == ("man-f1-zz",)
    assert [c.code for c in reading.contours] == ["man-f1-a"]


def test_a_space_with_no_path_yields_no_contour_of_its_own():
    """A space with no path is not on the plan — no invented shape is drawn for it."""
    reading = read_plan(svg(contour("man-f1-a")), ["man-f1-a", "man-f1-b"])

    assert [c.code for c in reading.contours] == ["man-f1-a"]


def test_a_file_with_no_paths_at_all_is_a_plan_with_no_contours():
    """A plan finds what has not been recorded, so it loads even against an empty tree."""
    reading = read_plan(svg(""), ["man-f1-a"])

    assert reading.contours == ()
    assert reading.unmatched == ()


def test_a_path_carrying_an_id_but_no_geometry_is_not_a_contour():
    """A contour is a shape; a path without `d` defines none and bounds no space."""
    reading = read_plan(svg('<path id="man-f1-a" />'), ["man-f1-a"])

    assert reading.contours == ()


# Rejections: a file that is not a plan


def test_a_file_without_a_viewbox_is_rejected():
    """Without a `viewBox` there is nothing to align contours with: it declares the axes."""
    with pytest.raises(PlanUnreadable, match="viewBox"):
        read_plan(svg(contour("man-f1-a"), view_box=None), ["man-f1-a"])


def test_a_viewbox_that_is_not_four_numbers_is_rejected():
    """A broken `viewBox` is worse than a missing one: it looks like it works."""
    with pytest.raises(PlanUnreadable, match="viewBox"):
        read_plan(svg(contour("man-f1-a"), view_box="0 0 100"), ["man-f1-a"])


def test_a_viewbox_with_no_extent_is_rejected():
    """A plan of zero width cannot be drawn, and dividing by its size is an error on the screen."""
    with pytest.raises(PlanUnreadable, match="viewBox"):
        read_plan(svg(contour("man-f1-a"), view_box="0 0 0 100"), ["man-f1-a"])


def test_a_file_that_is_not_xml_is_rejected():
    """The wrong file was uploaded — a reason to reject, not an empty plan on screen."""
    with pytest.raises(PlanUnreadable):
        read_plan(b"%PDF-1.7 \n1 0 obj", ["man-f1-a"])


def test_an_xml_file_that_is_not_svg_is_rejected():
    """It parsed all right, but it is not a plan."""
    with pytest.raises(PlanUnreadable, match="SVG"):
        read_plan("<drawing><path id='man-f1-a' d='M0 0'/></drawing>", ["man-f1-a"])


def test_two_paths_outlining_one_space_are_rejected():
    """A space has one contour on a plan: two shapes raise the question of which is right."""
    with pytest.raises(PlanUnreadable, match="man-f1-a"):
        read_plan(svg(contour("man-f1-a") + contour("man-f1-a", d="M5 5 L6 6 Z")), ["man-f1-a"])


def test_the_same_id_on_two_paths_of_no_space_does_not_reject_the_file():
    """A repeated typo is still the same typo: the plan loads and shows it.

    A rejection here would mean a plan cannot be uploaded until the tree of spaces is
    flawless — and it exists precisely to make the gaps in that tree visible.
    """
    reading = read_plan(svg(contour("man-f1-zz") + contour("man-f1-zz")), ["man-f1-a"])

    assert reading.unmatched == ("man-f1-zz", "man-f1-zz")


# The coordinate system of a plan


def test_the_viewbox_is_carried_out_of_the_file():
    """The overlaid layer of contours gets the same `viewBox` — otherwise they drift apart."""
    reading = read_plan(svg(contour("man-f1-a"), view_box="-10 -20 800 600"), ["man-f1-a"])

    assert reading.view_box == "-10 -20 800 600"


def test_the_viewbox_is_normalised_to_the_numbers_it_carries():
    """In a file the separator may be a comma or a newline; one single form reaches the screen."""
    reading = read_plan(svg("", view_box="0,0\n800, 600"), [])

    assert reading.view_box == "0 0 800 600"

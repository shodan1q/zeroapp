"""Tests for icon design parsing, fitting and rendering."""

from __future__ import annotations

import io

import pytest

from zerodev.generator.icon_designer import (
    FOREGROUND_SAFE_ZONE,
    IconDesignError,
    IconSpec,
    design_bounds,
    fallback_spec,
    fit_to_safe_zone,
    parse_color,
    parse_icon_response,
    render_layers,
)

SPEC_JSON = """
{
  "concept": "an orbit around a core",
  "background": {"type": "radial", "from": "#3B2A7A", "to": "#0B0A1F"},
  "marks": [
    {"shape": "ring", "cx": 0.5, "cy": 0.5, "r": 0.30, "width": 0.03, "stroke": "#FFFFFF"},
    {"shape": "circle", "cx": 0.5, "cy": 0.5, "r": 0.12, "fill": "#FFD98A"}
  ]
}
"""


# ── Parsing ─────────────────────────────────────────────────────


def test_parse_icon_response_reads_marks() -> None:
    spec = parse_icon_response(SPEC_JSON)
    assert spec.concept.startswith("an orbit")
    assert len(spec.marks) == 2


def test_parse_icon_response_tolerates_fences_and_prose() -> None:
    spec = parse_icon_response(f"Here it is:\n```json\n{SPEC_JSON}\n```\nhope that helps")
    assert len(spec.marks) == 2


def test_unknown_shapes_dropped() -> None:
    spec = parse_icon_response('{"marks": [{"shape": "unicorn"}, {"shape": "circle", "cx": 0.5, "cy": 0.5, "r": 0.2}]}')
    assert [m["shape"] for m in spec.marks] == ["circle"]


def test_spec_with_no_renderable_marks_rejected() -> None:
    with pytest.raises(IconDesignError, match="no renderable marks"):
        parse_icon_response('{"marks": [{"shape": "unicorn"}]}')


def test_garbage_response_rejected() -> None:
    with pytest.raises(IconDesignError):
        parse_icon_response("I cannot design that")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("#FFF", (255, 255, 255)), ("#0A84FF", (10, 132, 255)), ("bogus", (10, 132, 255)), (None, (10, 132, 255))],
)
def test_parse_color(value, expected) -> None:
    assert parse_color(value) == expected


# ── Composition ─────────────────────────────────────────────────


def test_fit_scales_a_timid_design_up() -> None:
    tiny = IconSpec(marks=[{"shape": "circle", "cx": 0.5, "cy": 0.5, "r": 0.05}])
    fit_to_safe_zone(tiny)
    x0, y0, x1, y1 = design_bounds(tiny)
    assert x1 - x0 == pytest.approx(FOREGROUND_SAFE_ZONE, abs=0.02)


def test_fit_pulls_an_overflowing_design_in() -> None:
    huge = IconSpec(marks=[{"shape": "circle", "cx": 0.5, "cy": 0.5, "r": 0.95}])
    fit_to_safe_zone(huge)
    x0, y0, x1, y1 = design_bounds(huge)
    assert x1 - x0 == pytest.approx(FOREGROUND_SAFE_ZONE, abs=0.02)
    assert x0 > 0 and y0 > 0 and x1 < 1 and y1 < 1


def test_fit_centres_an_off_centre_design() -> None:
    lopsided = IconSpec(marks=[{"shape": "circle", "cx": 0.25, "cy": 0.3, "r": 0.1}])
    fit_to_safe_zone(lopsided)
    x0, y0, x1, y1 = design_bounds(lopsided)
    assert (x0 + x1) / 2 == pytest.approx(0.5, abs=0.02)
    assert (y0 + y1) / 2 == pytest.approx(0.5, abs=0.02)


def test_strokes_never_shrink_below_the_legibility_floor() -> None:
    spec = IconSpec(marks=[{"shape": "ring", "cx": 0.5, "cy": 0.5, "r": 0.9, "width": 0.026}])
    fit_to_safe_zone(spec)
    assert spec.marks[0]["width"] >= 0.02


# ── Fallback ────────────────────────────────────────────────────


def test_fallback_is_deterministic() -> None:
    assert fallback_spec("深空信标", "#7C4DFF").marks == fallback_spec("深空信标", "#7C4DFF").marks


def test_fallback_variants_spread_across_names() -> None:
    # sum(ord(...)) collapsed six CJK names onto three variants; a digest must not.
    names = ["深空信标", "考研数三公式速查", "晨间习惯", "记账本", "星图", "单词卡", "静心冥想", "潮汐"]
    shapes = {tuple(m["shape"] for m in fallback_spec(n, "#0A84FF").marks) for n in names}
    assert len(shapes) >= 3


def test_fallback_contains_no_text() -> None:
    # The whole point of the rewrite: a mark, not a letter on a gradient.
    for mark in fallback_spec("深空信标", "#0A84FF").marks:
        assert mark["shape"] in {"circle", "ring", "arc", "polygon", "line", "rect", "triangle"}


# ── Rendering ───────────────────────────────────────────────────


def test_render_produces_three_layers() -> None:
    from PIL import Image

    spec = fit_to_safe_zone(parse_icon_response(SPEC_JSON))
    background, foreground, composite = render_layers(spec, "#7C4DFF", size=128)

    bg = Image.open(io.BytesIO(background))
    fg = Image.open(io.BytesIO(foreground)).convert("RGBA")
    comp = Image.open(io.BytesIO(composite)).convert("RGBA")

    assert bg.size == fg.size == comp.size == (128, 128)
    # Background is full-bleed, foreground is a transparent mark, composite is flat.
    assert fg.getchannel("A").getextrema()[0] == 0
    assert comp.getchannel("A").getextrema() == (255, 255)


def test_rendered_mark_is_centred_and_well_sized() -> None:
    from PIL import Image

    spec = fit_to_safe_zone(parse_icon_response(SPEC_JSON))
    _, foreground, _ = render_layers(spec, "#7C4DFF", size=256)
    box = Image.open(io.BytesIO(foreground)).getchannel("A").getbbox()

    width = (box[2] - box[0]) / 256
    assert 0.45 < width < 0.85, f"mark occupies {width:.0%} of the tile"
    assert abs((box[0] + box[2]) / 2 / 256 - 0.5) < 0.06


def test_malformed_mark_does_not_lose_the_icon() -> None:
    from PIL import Image

    spec = IconSpec(
        marks=[
            {"shape": "polygon", "points": "not-a-list"},
            {"shape": "circle", "cx": 0.5, "cy": 0.5, "r": 0.3, "fill": "#FFFFFF"},
        ]
    )
    _, foreground, _ = render_layers(fit_to_safe_zone(spec), "#0A84FF", size=64)
    assert Image.open(io.BytesIO(foreground)).getchannel("A").getbbox() is not None

"""Design and render HarmonyOS layered app icons.

The previous approach -- a flat gradient with the app's first character stamped
on it -- reads as a placeholder, because that is what it is. A letter is not a
mark. This module instead lets the model *design* the icon: it returns a small
JSON document describing the artwork with geometric primitives, and this module
renders that deterministically with Pillow.

A restricted vocabulary rather than raw SVG is a deliberate trade. Rasterising
SVG would mean a Cairo system dependency, and the freedom would mostly be spent
on paths that render badly at launcher sizes anyway. Circles, rings, arcs,
polygons and strokes cover the vocabulary of real app marks, and every one of
them can be drawn crisply.

Rendering notes that matter at icon sizes:

- Everything is drawn at 4x and downsampled with LANCZOS. Pillow's draw
  primitives are not anti-aliased, so this is the difference between clean
  edges and visible stair-stepping.
- Coordinates are normalised 0..1, so one spec renders at any size.
- Foreground artwork is kept inside a safe zone. The HarmonyOS launcher masks
  and parallax-shifts the foreground layer, so anything near the edge gets cut.
"""

from __future__ import annotations

import colorsys
import hashlib
import io
import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Render scale for anti-aliasing. Pillow's shapes are hard-edged, so drawing
# large and downsampling is what produces smooth curves.
SUPERSAMPLE = 4

# The launcher masks the foreground layer; art outside this fraction of the
# canvas can be clipped on some device shapes.
FOREGROUND_SAFE_ZONE = 0.62

ICON_SIZE = 1024

SHAPES = ("circle", "ring", "arc", "polygon", "line", "rect", "triangle")

ICON_PROMPT = """\
Design the app icon as a geometric mark.

APP: {app_name}
Description: {description}
Visual direction: {mood}
Brand colour: {accent}

Return ONLY a JSON object:

{{
  "concept": "one sentence: what the mark depicts and why it suits this app",
  "background": {{
    "type": "linear" | "radial",
    "from": "#RRGGBB",
    "to": "#RRGGBB",
    "angle": 135
  }},
  "marks": [
    {{"shape": "circle",   "cx": 0.5, "cy": 0.5, "r": 0.18, "fill": "#RRGGBB", "opacity": 1.0}},
    {{"shape": "ring",     "cx": 0.5, "cy": 0.5, "r": 0.30, "width": 0.035, "stroke": "#RRGGBB"}},
    {{"shape": "arc",      "cx": 0.5, "cy": 0.5, "r": 0.38, "start": 200, "end": 340,
      "width": 0.03, "stroke": "#RRGGBB"}},
    {{"shape": "line",     "from": [0.3, 0.7], "to": [0.7, 0.3], "width": 0.03, "stroke": "#RRGGBB"}},
    {{"shape": "polygon",  "points": [[0.5,0.28],[0.68,0.66],[0.32,0.66]], "fill": "#RRGGBB"}},
    {{"shape": "triangle", "cx": 0.5, "cy": 0.5, "r": 0.22, "rotation": 0, "fill": "#RRGGBB"}},
    {{"shape": "rect",     "x": 0.35, "y": 0.45, "w": 0.30, "h": 0.10, "radius": 0.05, "fill": "#RRGGBB"}}
  ]
}}

DESIGN RULES:
  - The mark must READ AT 48 PIXELS. Two to six shapes. No fine detail, no thin hairlines,
    no text, no letters, no numbers, no emoji.
  - Depict the app's subject concretely -- an orbit, a signal arc, a leaf, a waveform --
    rather than an abstract blob. Someone should be able to name what it is.
  - Compose within the centre: keep every coordinate between 0.18 and 0.82. The launcher
    masks the edges.
  - Strong figure/ground contrast against the background gradient. Light marks on a deep
    gradient usually win.
  - Stroke widths at least 0.025 so they survive downscaling.
  - All coordinates and sizes are fractions of the canvas, between 0 and 1.

No commentary, no fences.
"""


class IconDesignError(ValueError):
    """Raised when an icon specification cannot be used."""


@dataclass
class IconSpec:
    """A renderable icon design."""

    concept: str = ""
    background: dict[str, Any] = field(default_factory=dict)
    marks: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Any) -> IconSpec:
        """Validate a model-produced spec, dropping marks it cannot render."""
        if not isinstance(payload, dict):
            raise IconDesignError(f"Icon spec must be an object, got {type(payload).__name__}.")

        marks = [m for m in (payload.get("marks") or []) if isinstance(m, dict) and m.get("shape") in SHAPES]
        if not marks:
            raise IconDesignError("Icon spec contained no renderable marks.")

        background = payload.get("background")
        if not isinstance(background, dict):
            background = {}
        return cls(concept=str(payload.get("concept", "")), background=background, marks=marks)


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------


def parse_color(value: Any, fallback: tuple[int, int, int] = (10, 132, 255)) -> tuple[int, int, int]:
    """Parse ``#rgb`` / ``#rrggbb`` into an RGB triple."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return tuple(max(0, min(255, int(c))) for c in value[:3])  # type: ignore[return-value]
        except (TypeError, ValueError):
            return fallback
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return fallback
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return fallback


def _shift(rgb: tuple[int, int, int], *, lightness: float = 0.0, saturation: float = 0.0) -> tuple[int, int, int]:
    """Nudge a colour in HLS space, used to derive gradient stops."""
    h, light, sat = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    light = max(0.0, min(1.0, light + lightness))
    sat = max(0.0, min(1.0, sat + saturation))
    return tuple(int(round(c * 255)) for c in colorsys.hls_to_rgb(h, light, sat))  # type: ignore[return-value]


def _rotate_hue(rgb: tuple[int, int, int], degrees: float) -> tuple[int, int, int]:
    h, light, sat = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    h = (h + degrees / 360.0) % 1.0
    return tuple(int(round(c * 255)) for c in colorsys.hls_to_rgb(h, light, sat))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Fallback design
# ---------------------------------------------------------------------------


def fallback_spec(app_name: str, accent: str) -> IconSpec:
    """A geometric mark derived from the app name, when no design is available.

    Deterministic on the name, so the same app always gets the same icon, and
    still a composition rather than a letter on a gradient.
    """
    base = parse_color(accent)
    # A digest spreads evenly; sum(ord(...)) clusters badly for CJK names
    # (six sample names collapsed onto three variants).
    digest = hashlib.sha1(app_name.encode("utf-8")).digest()
    variant = digest[0] % 4
    light = "#FFFFFF"

    if variant == 0:  # orbit
        marks = [
            {"shape": "ring", "cx": 0.5, "cy": 0.5, "r": 0.30, "width": 0.030, "stroke": light, "opacity": 0.55},
            {"shape": "circle", "cx": 0.5, "cy": 0.5, "r": 0.14, "fill": light},
            {"shape": "circle", "cx": 0.5, "cy": 0.20, "r": 0.055, "fill": light},
        ]
    elif variant == 1:  # signal arcs
        marks = [
            {
                "shape": "arc",
                "cx": 0.5,
                "cy": 0.70,
                "r": 0.34,
                "start": 200,
                "end": 340,
                "width": 0.035,
                "stroke": light,
                "opacity": 0.45,
            },
            {
                "shape": "arc",
                "cx": 0.5,
                "cy": 0.70,
                "r": 0.22,
                "start": 200,
                "end": 340,
                "width": 0.035,
                "stroke": light,
                "opacity": 0.75,
            },
            {"shape": "circle", "cx": 0.5, "cy": 0.68, "r": 0.06, "fill": light},
        ]
    elif variant == 2:  # stacked layers
        marks = [
            {
                "shape": "rect",
                "x": 0.26,
                "y": 0.30,
                "w": 0.48,
                "h": 0.11,
                "radius": 0.055,
                "fill": light,
                "opacity": 0.45,
            },
            {
                "shape": "rect",
                "x": 0.26,
                "y": 0.45,
                "w": 0.48,
                "h": 0.11,
                "radius": 0.055,
                "fill": light,
                "opacity": 0.70,
            },
            {"shape": "rect", "x": 0.26, "y": 0.60, "w": 0.48, "h": 0.11, "radius": 0.055, "fill": light},
        ]
    else:  # ascending bars
        marks = [
            {
                "shape": "rect",
                "x": 0.26,
                "y": 0.56,
                "w": 0.12,
                "h": 0.20,
                "radius": 0.045,
                "fill": light,
                "opacity": 0.55,
            },
            {
                "shape": "rect",
                "x": 0.44,
                "y": 0.42,
                "w": 0.12,
                "h": 0.34,
                "radius": 0.045,
                "fill": light,
                "opacity": 0.78,
            },
            {"shape": "rect", "x": 0.62, "y": 0.28, "w": 0.12, "h": 0.48, "radius": 0.045, "fill": light},
        ]

    return IconSpec(
        concept="generated fallback mark",
        background={
            "type": "linear",
            "from": _rgb_hex(_shift(base, lightness=0.12, saturation=0.05)),
            "to": _rgb_hex(_shift(_rotate_hue(base, -12), lightness=-0.22)),
            "angle": 135,
        },
        marks=marks,
    )


def _rgb_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_layers(spec: IconSpec, accent: str, size: int = ICON_SIZE) -> tuple[bytes, bytes, bytes]:
    """Render ``(background_png, foreground_png, composite_png)``.

    HarmonyOS layered icons composite a full-bleed background under a
    transparent foreground so the launcher can animate them independently. The
    composite is returned too, because the splash-screen icon is a single flat
    image rather than a layered one.

    Only the foreground is supersampled. Gradients are smooth by construction,
    so drawing the background at 16x the pixels bought nothing and cost most of
    the render time; hard-edged shapes are the only thing that benefits.
    """
    from PIL import Image  # noqa: PLC0415 - heavy optional import

    background = _render_background(spec, accent, size)
    foreground = _render_foreground(spec, size * SUPERSAMPLE).resize((size, size), Image.LANCZOS)
    composite = Image.alpha_composite(background.convert("RGBA"), foreground)

    return _png(background.convert("RGB")), _png(foreground), _png(composite)


def _render_background(spec: IconSpec, accent: str, canvas: int):

    base = parse_color(accent)
    bg = spec.background if isinstance(spec.background, dict) else {}
    start = parse_color(bg.get("from"), _shift(base, lightness=0.12, saturation=0.05))
    end = parse_color(bg.get("to"), _shift(_rotate_hue(base, -12), lightness=-0.22))

    if str(bg.get("type", "linear")).lower() == "radial":
        image = _radial_gradient(canvas, start, end)
    else:
        try:
            angle = float(bg.get("angle", 135))
        except (TypeError, ValueError):
            angle = 135.0
        image = _linear_gradient(canvas, start, end, angle)

    return _vignette(image)


def _gradient_from_ramp(canvas: int, ramp, start: tuple[int, int, int], end: tuple[int, int, int]):
    """Turn a 0..1 interpolation array into an RGB image."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    ramp = np.clip(ramp, 0.0, 1.0)[..., None]
    begin = np.array(start, dtype=np.float32)
    finish = np.array(end, dtype=np.float32)
    pixels = (begin + (finish - begin) * ramp).astype(np.uint8)
    return Image.fromarray(pixels, mode="RGB").resize((canvas, canvas), Image.BICUBIC)


# Gradients are computed on a small grid and interpolated up. At icon sizes the
# result is indistinguishable from a per-pixel evaluation, and it turns a
# multi-million-iteration Python loop into a single vectorised expression.
_GRADIENT_GRID = 256


def _linear_gradient(canvas: int, start: tuple[int, int, int], end: tuple[int, int, int], angle: float):
    import numpy as np  # noqa: PLC0415

    grid = min(canvas, _GRADIENT_GRID)
    radians = math.radians(angle)
    dx, dy = math.cos(radians), math.sin(radians)
    span = abs(dx) + abs(dy) or 1.0

    axis = np.linspace(0.0, 1.0, grid, dtype=np.float32)
    fx, fy = np.meshgrid(axis, axis)
    # Project each point onto the gradient axis, normalised back into 0..1.
    ramp = ((fx - 0.5) * dx + (fy - 0.5) * dy) / span + 0.5
    return _gradient_from_ramp(canvas, ramp, start, end)


def _radial_gradient(canvas: int, start: tuple[int, int, int], end: tuple[int, int, int]):
    import numpy as np  # noqa: PLC0415

    grid = min(canvas, _GRADIENT_GRID)
    axis = np.linspace(-0.5, 0.5, grid, dtype=np.float32)
    fx, fy = np.meshgrid(axis, axis)
    ramp = np.hypot(fx, fy) / math.hypot(0.5, 0.5)
    return _gradient_from_ramp(canvas, ramp, start, end)


def _vignette(image):
    """Darken the corners slightly so the icon reads as a solid object."""
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415

    size = image.size[0]
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    inset = size * 0.06
    draw.ellipse([-inset, -inset, size + inset, size + inset], fill=90)
    mask = mask.filter(ImageFilter.GaussianBlur(size * 0.12))
    shade = Image.new("RGB", (size, size), (0, 0, 0))
    return Image.composite(image, Image.blend(image, shade, 0.16), mask)


def _render_foreground(spec: IconSpec, canvas: int):
    from PIL import Image, ImageDraw, ImageFilter  # noqa: PLC0415

    layer = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for mark in spec.marks:
        try:
            _draw_mark(draw, mark, canvas)
        except (TypeError, ValueError, KeyError) as exc:
            # One malformed mark must not lose the whole icon.
            logger.warning("Skipping unrenderable icon mark %s: %s", mark.get("shape"), exc)

    # A soft drop shadow lifts the mark off the gradient without looking heavy.
    alpha = layer.getchannel("A").filter(ImageFilter.GaussianBlur(canvas * 0.012))
    shadow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda a: int(a * 0.28)))
    offset = int(canvas * 0.008)
    shifted = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    shifted.paste(shadow, (0, offset))
    return Image.alpha_composite(shifted, layer)


def _draw_mark(draw, mark: dict[str, Any], canvas: int) -> None:
    """Render one primitive. Coordinates arrive normalised to 0..1."""
    shape = mark["shape"]
    opacity = _clamp01(mark.get("opacity", 1.0))
    fill = _rgba(mark.get("fill", "#FFFFFF"), opacity)
    stroke = _rgba(mark.get("stroke", mark.get("fill", "#FFFFFF")), opacity)

    def px(value: Any, default: float = 0.0) -> float:
        try:
            return float(value) * canvas
        except (TypeError, ValueError):
            return default * canvas

    if shape == "circle":
        cx, cy, r = px(mark.get("cx"), 0.5), px(mark.get("cy"), 0.5), px(mark.get("r"), 0.2)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)

    elif shape == "ring":
        cx, cy, r = px(mark.get("cx"), 0.5), px(mark.get("cy"), 0.5), px(mark.get("r"), 0.3)
        width = max(2, int(px(mark.get("width"), 0.03)))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=stroke, width=width)

    elif shape == "arc":
        cx, cy, r = px(mark.get("cx"), 0.5), px(mark.get("cy"), 0.5), px(mark.get("r"), 0.3)
        width = max(2, int(px(mark.get("width"), 0.03)))
        start = float(mark.get("start", 0))
        end = float(mark.get("end", 180))
        draw.arc([cx - r, cy - r, cx + r, cy + r], start=start, end=end, fill=stroke, width=width)

    elif shape == "line":
        a = mark.get("from") or [0.3, 0.5]
        b = mark.get("to") or [0.7, 0.5]
        width = max(2, int(px(mark.get("width"), 0.03)))
        draw.line(
            [float(a[0]) * canvas, float(a[1]) * canvas, float(b[0]) * canvas, float(b[1]) * canvas],
            fill=stroke,
            width=width,
            joint="curve",
        )

    elif shape == "polygon":
        points = [(float(p[0]) * canvas, float(p[1]) * canvas) for p in mark.get("points", []) if len(p) >= 2]
        if len(points) >= 3:
            draw.polygon(points, fill=fill)

    elif shape == "triangle":
        cx, cy, r = px(mark.get("cx"), 0.5), px(mark.get("cy"), 0.5), px(mark.get("r"), 0.22)
        rotation = math.radians(float(mark.get("rotation", 0)) - 90)
        points = [
            (cx + r * math.cos(rotation + i * 2 * math.pi / 3), cy + r * math.sin(rotation + i * 2 * math.pi / 3))
            for i in range(3)
        ]
        draw.polygon(points, fill=fill)

    elif shape == "rect":
        x, y = px(mark.get("x"), 0.3), px(mark.get("y"), 0.4)
        w, h = px(mark.get("w"), 0.4), px(mark.get("h"), 0.2)
        radius = px(mark.get("radius"), 0.04)
        draw.rounded_rectangle([x, y, x + w, y + h], radius=max(0, radius), fill=fill)


def _rgba(value: Any, opacity: float) -> tuple[int, int, int, int]:
    r, g, b = parse_color(value, (255, 255, 255))
    return (r, g, b, int(round(255 * _clamp01(opacity))))


def _clamp01(value: Any, default: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return 0.0 if number < 0 else 1.0 if number > 1 else number


def _png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n(.*?)\n?\s*```\s*$", re.DOTALL)


def parse_icon_response(text: str) -> IconSpec:
    """Parse a model response into an :class:`IconSpec`."""
    cleaned = text.strip()
    fenced = _FENCE_RE.match(cleaned)
    if fenced:
        cleaned = fenced.group(1)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise IconDesignError(f"Icon response was not JSON: {cleaned[:200]}") from None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise IconDesignError(f"Could not parse icon JSON: {exc}") from exc
    return IconSpec.from_payload(payload)


def design_bounds(spec: IconSpec) -> tuple[float, float, float, float]:
    """Bounding box of the artwork in normalised space, stroke widths included."""
    xs: list[float] = []
    ys: list[float] = []

    def add(x: float, y: float) -> None:
        xs.append(x)
        ys.append(y)

    for mark in spec.marks:
        shape = mark.get("shape")
        half_stroke = _clamp01(mark.get("width", 0.0), 0.0) / 2
        if shape in ("circle", "ring", "arc", "triangle"):
            cx, cy = _clamp01(mark.get("cx"), 0.5), _clamp01(mark.get("cy"), 0.5)
            r = _clamp01(mark.get("r"), 0.2) + half_stroke
            add(cx - r, cy - r)
            add(cx + r, cy + r)
        elif shape == "rect":
            x, y = _clamp01(mark.get("x"), 0.3), _clamp01(mark.get("y"), 0.4)
            add(x, y)
            add(x + _clamp01(mark.get("w"), 0.4), y + _clamp01(mark.get("h"), 0.2))
        elif shape == "line":
            for key in ("from", "to"):
                point = mark.get(key)
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    add(_clamp01(point[0], 0.5) - half_stroke, _clamp01(point[1], 0.5) - half_stroke)
                    add(_clamp01(point[0], 0.5) + half_stroke, _clamp01(point[1], 0.5) + half_stroke)
        elif shape == "polygon":
            for point in mark.get("points", []) or []:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    add(_clamp01(point[0], 0.5), _clamp01(point[1], 0.5))

    if not xs or not ys:
        return (0.0, 0.0, 1.0, 1.0)
    return (min(xs), min(ys), max(xs), max(ys))


def fit_to_safe_zone(spec: IconSpec, safe_zone: float = FOREGROUND_SAFE_ZONE) -> IconSpec:
    """Scale and centre the artwork so it fills the launcher-safe area.

    Fitting rather than merely clamping is what gives every generated icon the
    same optical weight. A design that came back timid gets enlarged, one that
    overflows gets pulled in, and either way the mark ends up centred and
    occupying a consistent fraction of the tile -- which is most of what makes a
    set of icons look deliberate rather than automatic.
    """
    x0, y0, x1, y1 = design_bounds(spec)
    width, height = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    scale = safe_zone / max(width, height)
    # Centre the scaled bounding box on the canvas centre.
    offset_x = 0.5 - (x0 + width / 2) * scale
    offset_y = 0.5 - (y0 + height / 2) * scale

    def map_x(value: Any, default: float = 0.5) -> float:
        return _clamp01(value, default) * scale + offset_x

    def map_y(value: Any, default: float = 0.5) -> float:
        return _clamp01(value, default) * scale + offset_y

    def map_size(value: Any) -> float:
        try:
            return float(value) * scale
        except (TypeError, ValueError):
            return 0.0

    for mark in spec.marks:
        if "cx" in mark:
            mark["cx"] = map_x(mark["cx"])
        if "cy" in mark:
            mark["cy"] = map_y(mark["cy"])
        if "x" in mark:
            mark["x"] = map_x(mark["x"], 0.3)
        if "y" in mark:
            mark["y"] = map_y(mark["y"], 0.4)
        for key in ("r", "w", "h", "radius"):
            if key in mark:
                mark[key] = map_size(mark[key])
        if "width" in mark:
            # Strokes scale with the art, but never below what survives a
            # downscale to launcher size.
            mark["width"] = max(map_size(mark["width"]), 0.02)
        for key in ("from", "to"):
            point = mark.get(key)
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                mark[key] = [map_x(point[0]), map_y(point[1])]
        points = mark.get("points")
        if isinstance(points, list):
            mark["points"] = [
                [map_x(p[0]), map_y(p[1])] for p in points if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
    return spec

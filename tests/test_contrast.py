"""WCAG AA contrast for the console's colour tokens (web/src/index.css): every text colour on every surface it is used
on reaches 4.5:1, in the light theme, the dark theme and the emergency takeover."""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parent.parent / "web" / "src" / "index.css").read_text(encoding="utf-8")


def block(selector):
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\n  \}", CSS, flags=re.S)
    assert m, selector
    return dict(re.findall(r"--([a-z-]+):\s*([\d.]+ [\d.]+% [\d.]+%)", m.group(1)))


def rgb(hsl):
    h, s, l = (float(v.rstrip("%")) for v in hsl.split())
    s, l = s / 100, l / 100
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return [v + m for v in (r, g, b)]


def luminance(hsl):
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb(hsl))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


LIGHT = block(":root")
DARK = {**LIGHT, **block(".dark")}
EMERGENCY = {**DARK, **block(".em-theme")}

PAIRS = [
    ("foreground", "background"), ("foreground", "card"), ("muted-foreground", "card"), ("muted-foreground", "background"),
    ("muted-foreground", "muted"), ("primary", "card"), ("primary", "primary-soft"), ("primary-foreground", "primary"),
    ("ok", "card"), ("warn", "card"), ("crit", "card"), ("off", "card"),
    ("ok", "ok-soft"), ("warn", "warn-soft"), ("crit", "crit-soft"), ("off", "off-soft"), ("warn", "background"),
    # overview: brand-coloured headings, the active navigation item, text on the tinted cards
    ("heading", "card"), ("heading", "background"), ("heading", "nav-active"), ("heading", "sidebar"),
    ("foreground", "warn-soft"), ("foreground", "off-soft"), ("muted-foreground", "warn-soft"), ("muted-foreground", "off-soft"),
    ("foreground", "muted"),
    ("heading", "muted"),  # the threshold label on the band above the threshold (live signal chart)
    # the frame: sidebar rows, the live chip, the outlined "Start emergency mode" button, the Ask NADI bubbles
    ("foreground", "sidebar"), ("muted-foreground", "sidebar"), ("foreground", "nav-active"), ("foreground", "ok-soft"),
    ("crit", "background"), ("foreground", "primary-soft"), ("foreground", "accent"),
]
# Brand marks and lines (logo, signal line, chart line, markers) are graphics, not text: 3:1 against their surface.
GRAPHICS = [("brand", "card"), ("brand", "background"), ("brand-grey", "card"), ("off", "card"), ("ok", "card"), ("warn", "card"),
            ("brand", "muted")]  # the signal line where it crosses the band above the threshold


@pytest.mark.parametrize("theme,tokens", [("light", LIGHT), ("dark", DARK)])
@pytest.mark.parametrize("text,surface", PAIRS)
def test_text_tokens_reach_aa(theme, tokens, text, surface):
    assert ratio(tokens[text], tokens[surface]) >= 4.5, (theme, text, surface, round(ratio(tokens[text], tokens[surface]), 2))


@pytest.mark.parametrize("theme,tokens", [("light", LIGHT), ("dark", DARK)])
@pytest.mark.parametrize("mark,surface", GRAPHICS)
def test_graphic_tokens_reach_3_to_1(theme, tokens, mark, surface):
    assert ratio(tokens[mark], tokens[surface]) >= 3, (theme, mark, surface, round(ratio(tokens[mark], tokens[surface]), 2))


def over(top, under, alpha):
    """The colour seen when `top` is painted at `alpha` over `under`, as "r g b" fractions for contrast()."""
    return [t * alpha + u * (1 - alpha) for t, u in zip(rgb(top), rgb(under))]


def contrast(text_rgb, surface_rgb):
    def lum(c):
        r, g, b = (v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    la, lb = sorted((lum(text_rgb), lum(surface_rgb)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# The floor-plan tiles are tints, not tokens: 15% of the status colour over the floor (occupied, waste), 40% of the
# muted surface (no sensor). The words on them are 14 px and up.
TILES = [("ok", 0.15, "ok"), ("ok", 0.15, "foreground"), ("warn", 0.15, "warn"), ("warn", 0.15, "foreground"),
         ("muted", 0.40, "off"), ("muted", 0.40, "foreground"), ("plan-floor", 1, "muted-foreground"), ("plan-floor", 1, "off")]


@pytest.mark.parametrize("theme,tokens", [("light", LIGHT), ("dark", DARK)])
@pytest.mark.parametrize("fill,alpha,text", TILES)
def test_words_on_the_floor_plan_tiles_reach_aa(theme, tokens, fill, alpha, text):
    surface = over(tokens[fill], tokens["plan-floor"], alpha)
    assert contrast(rgb(tokens[text]), surface) >= 4.5, (theme, text, fill, round(contrast(rgb(tokens[text]), surface), 2))


def test_white_on_the_logo_mark_and_exit_sign():
    """White on the brand teal (a graphic: 3:1); the EXIT sign is white text on a fixed dark green."""
    white = "0 0% 100%"
    assert ratio(white, LIGHT["brand"]) >= 3 and ratio(white, DARK["brand"]) >= 3
    assert ratio(white, "151 56% 27%") >= 4.5  # #1E6B45


@pytest.mark.parametrize("text,surface", [("foreground", "background"), ("foreground", "card"), ("muted-foreground", "card"),
                                          ("crit", "card"), ("crit", "background"), ("warn", "card"), ("ok", "card")])
def test_emergency_takeover_reaches_aa(text, surface):
    assert ratio(EMERGENCY[text], EMERGENCY[surface]) >= 4.5, (text, surface, round(ratio(EMERGENCY[text], EMERGENCY[surface]), 2))

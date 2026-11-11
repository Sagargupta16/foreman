#!/usr/bin/env python3
"""Draw docs/how-it-works/*.svg, the animated README figure of one dispatch run.

  python scripts/how_it_works_svg.py

Writes four files: dark and light, for desktop (880 wide) and for phones (320 wide).
The run shown is examples/feature-plan.json as `plan.py check` routes it: 6 subtasks in
3 waves, Haiku 2 and Sonnet 4. Standard library only, and the output is deterministic.
SMIL only, no script or external references, so it animates inside a README <img>.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "how-it-works"
P = "fmhw"  # id and class prefix
T = 18  # seconds per loop
F = 0.008  # fade, as a fraction of T
RESET = 0.968  # from here every state fades back to queued for the next loop

TASK = "Add CSV export to the users API and a download button on the users page"

# id, kind, model tier, wave (examples/feature-plan.json through plan.py check)
SUBTASKS = [
    ("map", "locate", "haiku", 1),
    ("build-api", "implement", "sonnet", 2),
    ("build-ui", "implement", "sonnet", 2),
    ("docs", "mechanical", "haiku", 3),
    ("review", "review", "sonnet", 3),
    ("verify", "verify", "sonnet", 3),
]

# launch is when the packet leaves the gate; it arrives TRAVEL later
TRAVEL = 0.04
TIMES = {
    "map": {"launch": 0.27, "run": [(0.31, 0.36)], "done": 0.36},
    "build-api": {"launch": 0.385, "run": [(0.425, 0.50)], "done": 0.50},
    "build-ui": {
        "launch": 0.385,
        "run": [(0.425, 0.47), (0.53, 0.575)],
        "partial": (0.47, 0.53),
        "done": 0.575,
    },
    "docs": {"launch": 0.59, "run": [(0.63, 0.68)], "done": 0.68},
    "review": {"launch": 0.59, "run": [(0.63, 0.69)], "done": 0.69},
    "verify": {"launch": 0.59, "run": [(0.63, 0.70)], "done": 0.70},
}

STEPS = [
    ("1 REQUEST", 0.0),
    ("2 PLAN", 0.08),
    ("3 CHECK", 0.18),
    ("4 WAVES", 0.26),
    ("5 VERIFY", 0.72),
    ("6 LOG", 0.82),
]

CAPTIONS = [
    (0.0, "A request comes in. A one-unit task is done inline, with no agents."),
    (
        0.08,
        "The feature template splits it into 6 subtasks, "
        "each with the files it owns and one check.",
    ),
    (
        0.18,
        "plan.py check runs before any agent starts: "
        "no shared files in a wave, no silent model changes.",
    ),
    (0.26, "Wave 1: the scout maps the code on Haiku."),
    (0.375, "Wave 2: two builders run in parallel on Sonnet, and build-ui stops short."),
    (
        0.525,
        "A short stop reruns once on the same model at higher effort; "
        "a wrong answer goes one tier up.",
    ),
    (0.585, "Wave 3: docs on Haiku, review and verify on Sonnet, all at once."),
    (
        0.71,
        "The foreman checks every changed file against its owner, "
        "runs the tests once, reads the diff.",
    ),
    (0.82, "Each outcome goes to the run log, and plan.py stats turns the log into tune hints."),
]

GATE_OK = 0.21
VERIFY_PACKET = (0.72, 0.745)
VERIFY_TICKS = [0.755, 0.775, 0.795]
LOG_PACKET = (0.82, 0.835)
LOG_TICKS = [0.845, 0.865]

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "panel": "#151b23",
        "lane": "#1b222c",
        "chip": "#0d1117",
        "line": "#656d76",
        "text": "#e6edf3",
        "muted": "#9198a1",
        "accent": "#4493f8",
        "accent_fill": "rgba(68,147,248,0.18)",
        "ok": "#3fb950",
        "ok_fill": "rgba(63,185,80,0.14)",
        "warn": "#d29922",
        "warn_fill": "rgba(210,153,34,0.18)",
        "ink": "#0d1117",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f6f8fa",
        "lane": "#eef1f4",
        "chip": "#ffffff",
        "line": "#818b98",
        "text": "#1f2328",
        "muted": "#59636e",
        "accent": "#0969da",
        "accent_fill": "rgba(9,105,218,0.12)",
        "ok": "#1a7f37",
        "ok_fill": "rgba(26,127,55,0.12)",
        "warn": "#9a6700",
        "warn_fill": "rgba(154,103,0,0.14)",
        "ink": "#ffffff",
    },
}

SANS = "'Segoe UI',-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"


def n(v: float) -> str:
    """A number as short as it can be written."""
    text = f"{v:.4f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


# animation helpers: one clock, every element on dur=T


def spans_pts(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Opacity 1 inside each (start, end) span and 0 outside, with short fades."""
    pts: list[tuple[float, float]] = []
    for a, b in spans:
        pts += [(0.0, 1.0)] if a <= 0 else [(a, 0.0), (a + F, 1.0)]
        pts += [(1.0, 1.0)] if b >= 1 else [(b, 1.0), (b + F, 0.0)]
    if pts[0][0] > 0:
        pts.insert(0, (0.0, 0.0))
    if pts[-1][0] < 1:
        pts.append((1.0, 0.0))
    return pts


def animate(pts: list[tuple[float, float]], attr: str = "opacity") -> str:
    values = ";".join(n(v) for _, v in pts)
    times = ";".join(n(t) for t, _ in pts)
    return (
        f'<animate attributeName="{attr}" values="{values}" keyTimes="{times}" '
        f'dur="{T}s" repeatCount="indefinite"/>'
    )


def fade(spans: list[tuple[float, float]]) -> tuple[str, str]:
    """The opacity at t=0 and the animate element for these spans."""
    pts = spans_pts(spans)
    return n(pts[0][1]), animate(pts)


def move(stops: list[tuple[float, tuple[float, float]]]) -> str:
    """Translate that holds each (x, y) from its time until the next stop."""
    pts: list[tuple[float, tuple[float, float]]] = []
    prev = stops[0][1]
    for i, (t, pos) in enumerate(stops):
        if i == 0:
            pts.append((0.0, pos))
        else:
            pts += [(t, prev), (t + F, pos)]
        prev = pos
    pts.append((1.0, prev))
    values = ";".join(f"{n(x)} {n(y)}" for _, (x, y) in pts)
    times = ";".join(n(t) for t, _ in pts)
    return (
        f'<animateTransform attributeName="transform" type="translate" values="{values}" '
        f'keyTimes="{times}" dur="{T}s" repeatCount="indefinite"/>'
    )


def packet(path: str, start: float, end: float, c: dict) -> str:
    times = f"0;{n(start)};{n(end)};1"
    first, op = fade([(start, end + 0.006)])
    return (
        f'<circle r="3.6" fill="{c["accent"]}" opacity="{first}">'
        f'<animateMotion path="{path}" keyPoints="0;0;1;1" keyTimes="{times}" '
        f'calcMode="linear" dur="{T}s" repeatCount="indefinite"/>{op}</circle>'
    )


# drawing helpers


def text(x: float, y: float, s: str, c: str, size: float, cls: str = "s", **kw: str) -> str:
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in kw.items())
    return (
        f'<text class="{P}-{cls}" x="{n(x)}" y="{n(y)}" fill="{c}" '
        f'font-size="{n(size)}"{extra}>{escape(s)}</text>'
    )


def rect(x: float, y: float, w: float, h: float, r: float, fill: str, stroke: str = "") -> str:
    s = f' stroke="{stroke}"' if stroke else ""
    return (
        f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" rx="{n(r)}" fill="{fill}"{s}/>'
    )


def check_mark(cx: float, cy: float, color: str) -> str:
    return (
        f'<path d="M{n(cx - 2.9)} {n(cy + 0.1)}L{n(cx - 0.8)} {n(cy + 2.2)}'
        f'L{n(cx + 3)} {n(cy - 2.3)}" fill="none" stroke="{color}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )


def bang(cx: float, cy: float, color: str) -> str:
    """An exclamation mark drawn as shapes, so no text sits on the badge."""
    return (
        f'<rect x="{n(cx - 0.9)}" y="{n(cy - 3.6)}" width="1.8" height="4.4" rx="0.9" '
        f'fill="{color}"/><circle cx="{n(cx)}" cy="{n(cy + 2.6)}" r="1" fill="{color}"/>'
    )


def badge(kind: str, cx: float, cy: float, c: dict) -> str:
    if kind == "queued":
        return (
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="5.2" fill="none" '
            f'stroke="{c["muted"]}" stroke-width="1.2"/>'
        )
    if kind == "run":
        return (
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="5.6" fill="{c["accent"]}"/>'
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="2" fill="{c["ink"]}"/>'
        )
    if kind == "warn":
        return f'<circle cx="{n(cx)}" cy="{n(cy)}" r="6" fill="{c["warn"]}"/>' + bang(
            cx, cy, c["ink"]
        )
    return f'<circle cx="{n(cx)}" cy="{n(cy)}" r="6" fill="{c["ok"]}"/>' + check_mark(
        cx, cy, c["ink"]
    )


def chip(sid: str, x: float, y: float, w: float, h: float, size: float, c: dict) -> list[str]:
    """A subtask chip: queued base, then run, partial and done overlays on the clock."""
    t = TIMES[sid]
    bx, by = x + w - 3, y + 3
    out = [
        rect(x, y, w, h, 6, c["chip"], c["line"]),
        text(x + 7, y + h / 2 + size * 0.36, sid, c["text"], size, "m"),
    ]
    layers = [("run", c["accent"], c["accent_fill"], t["run"])]
    if "partial" in t:
        layers.append(("warn", c["warn"], c["warn_fill"], [t["partial"]]))
    layers.append(("done", c["ok"], c["ok_fill"], [(t["done"], RESET)]))
    for kind, stroke, fill, spans in layers:
        first, op = fade(spans)
        out.append(
            f'<g opacity="{first}">{op}'
            f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" rx="6" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            f"{badge(kind, bx, by, c)}</g>"
        )
    return out


def ticked(cx: float, cy: float, at: float, c: dict) -> str:
    first, op = fade([(at, RESET)])
    return badge("queued", cx, cy, c) + f'<g opacity="{first}">{op}{badge("done", cx, cy, c)}</g>'


def chevron(x: float, y: float, c: dict, down: bool = False) -> str:
    d = (
        f"M{n(x - 3.5)} {n(y - 2)}L{n(x)} {n(y + 1.5)}L{n(x + 3.5)} {n(y - 2)}"
        if down
        else f"M{n(x - 2)} {n(y - 3.5)}L{n(x + 1.5)} {n(y)}L{n(x - 2)} {n(y + 3.5)}"
    )
    return (
        f'<path d="{d}" fill="none" stroke="{c["muted"]}" stroke-width="1.3" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )


def gate_result(x: float, y: float, size: float, c: dict) -> list[str]:
    """The checker's verdict: '...' until it passes, then the wave count it printed."""
    out = []
    for spans, label, color in [
        ([(0.0, GATE_OK), (RESET + F, 1.0)], "...", c["muted"]),
        ([(GATE_OK, RESET)], "ok, 3 waves", c["ok"]),
    ]:
        first, op = fade(spans)
        body = text(x, y, label, color, size, "m", text_anchor="end")
        out.append(f'<g opacity="{first}">{op}{body}</g>')
    return out


def label_on_lane(cx: float, y: float, s: str, c: dict) -> list[str]:
    """Muted centered text on a lane-colored backing, so the wave risers stop at it."""
    half = len(s) * 2.9 + 6
    return [
        rect(cx - half, y - 11, 2 * half, 15, 4, c["lane"]),
        text(cx, y, s, c["muted"], 10.5, text_anchor="middle"),
    ]


def wire(d: str, c: dict, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="3 3"' if dashed else ""
    return f'<path d="{d}" fill="none" stroke="{c["line"]}" stroke-width="1.3"{dash}/>'


# layouts


def desktop(c: dict) -> tuple[int, int, list[str]]:
    w, h = 880, 476
    o: list[str] = []
    o.append(text(24, 34, "FOREMAN / HOW A TASK RUNS", c["accent"], 11, "m", letter_spacing="1.4"))
    for i, (kind, label) in enumerate(
        [("queued", "queued"), ("run", "running"), ("warn", "rerun"), ("done", "done")]
    ):
        x = 600 + i * 66
        o.append(badge(kind, x, 30, c))
        o.append(text(x + 10, 34, label, c["muted"], 11))

    # step strip with one moving highlight
    pill_w, pill_y = 128, 50
    for i in range(len(STEPS)):
        o.append(rect(24 + i * 140, pill_y, pill_w, 26, 13, c["panel"]))
        if i:
            o.append(chevron(24 + i * 140 - 6, pill_y + 13, c))
    stops = [(t, (i * 140, 0)) for i, (_, t) in enumerate(STEPS)] + [(RESET, (0, 0))]
    o.append(
        f'<g>{move(stops)}<rect x="24" y="{pill_y}" width="{pill_w}" height="26" rx="13" '
        f'fill="{c["accent_fill"]}" stroke="{c["accent"]}" stroke-width="1.6"/></g>'
    )
    for i, (label, _) in enumerate(STEPS):
        o.append(
            text(
                24 + i * 140 + pill_w / 2,
                pill_y + 17,
                label,
                c["text"],
                11,
                "m",
                text_anchor="middle",
                letter_spacing="1",
            )
        )

    # panels
    top, bottom = 92, 412
    for x, pw, title in [(24, 232, "PLAN"), (268, 440, "ROUTE AND RUN"), (720, 136, "VERIFY, LOG")]:
        o.append(rect(x, top, pw, bottom - top, 10, c["panel"]))
        o.append(text(x + 12, top + 20, title, c["muted"], 10.5, "m", letter_spacing="1.2"))

    # plan panel
    o.append(rect(36, 122, 208, 72, 8, c["chip"], c["line"]))
    o.append(text(48, 140, "request", c["muted"], 10.5, "m"))
    for k, line in enumerate(wrap(TASK, 29)):
        o.append(text(48, 157 + k * 15, line, c["text"], 11.5))
    o.append(text(36, 214, "template: feature", c["muted"], 11, "m"))
    row0 = 224
    for k, (sid, kind, _, _) in enumerate(SUBTASKS):
        cy = row0 + 11 + k * 22
        o.append(text(44, cy + 4, sid, c["text"], 11.5, "m"))
        o.append(text(236, cy + 4, kind, c["muted"], 11, text_anchor="end"))
    sweep = [(0.0, (0, 0))] + [(0.09 + k * 0.013, (0, k * 22)) for k in range(1, 6)]
    first, op = fade([(0.08, 0.18)])
    o.append(
        f'<g opacity="{first}">{op}<g>{move(sweep)}'
        f'<rect x="36" y="{row0 + 1}" width="208" height="20" rx="5" fill="{c["accent_fill"]}"/>'
        f"</g></g>"
    )
    gate_y = 368
    o.append(rect(36, gate_y, 208, 32, 8, c["chip"], c["line"]))
    o.append(text(48, gate_y + 20, "plan.py check", c["text"], 11.5, "m"))
    o += gate_result(232, gate_y + 20, 11.5, c)
    bus_y = gate_y + 16

    # route and run panel: a model ladder, one column per wave
    cols = [392, 496, 600]
    col_w, chip_w, chip_h = 104, 92, 22
    for k, x in enumerate(cols):
        o.append(
            text(x + col_w / 2, 136, f"wave {k + 1}", c["muted"], 10.5, "m", text_anchor="middle")
        )
    lanes = {
        "haiku": (146, 50, ["scout, mechanic"]),
        "sonnet": (200, 80, ["builder, writer", "reviewer, verifier", "researcher"]),
        "opus": (284, 42, ["architect, debugger"]),
        "fable": (330, 42, ["specialist"]),
    }
    for name, (ly, lh, agents) in lanes.items():
        o.append(rect(276, ly, 424, lh, 6, c["lane"]))
        o.append(text(284, ly + 19, name, c["text"], 12.5, font_weight="700"))
        for k, a in enumerate(agents):
            o.append(text(284, ly + 33 + k * 13, a, c["muted"], 10.5))
    for x in cols:
        o.append(wire(f"M{x + 4} 146V{bus_y}", c))
    o.append(wire(f"M244 {bus_y}H{cols[-1] + 4}", c))
    # where each subtask sits
    slot = {}
    stack: dict[tuple[str, int], int] = {}
    for sid, _, tier, wave in SUBTASKS:
        ly, lh, _ = lanes[tier]
        k = stack.get((tier, wave), 0)
        stack[(tier, wave)] = k + 1
        x = cols[wave - 1] + (col_w - chip_w) / 2
        y = ly + 14 + k * 28 if tier == "sonnet" else ly + (lh - chip_h) / 2
        slot[sid] = (x, y)
    # the rerun ladder, static: wrong after a real try goes one tier up
    bx, by = slot["build-ui"]
    mid = bx + chip_w / 2
    o.append(wire(f"M{n(mid)} {n(by + chip_h + 1)}V{n(lanes['opus'][0] + 8)}", c, dashed=True))
    o.append(chevron(mid, lanes["opus"][0] + 8, c, down=True))
    o.append(text(mid, lanes["opus"][0] + 22, "failed:", c["muted"], 10.5, text_anchor="middle"))
    o.append(
        text(mid, lanes["opus"][0] + 35, "one tier up", c["muted"], 10.5, text_anchor="middle")
    )
    o += label_on_lane(cols[1] + col_w / 2, lanes["fable"][0] + 25, "not needed in this plan", c)
    for sid, _, _, _ in SUBTASKS:
        x, y = slot[sid]
        o += chip(sid, x, y, chip_w, chip_h, 11.5, c)
    for sid, _, _, wave in SUBTASKS:
        x, y = slot[sid]
        start = TIMES[sid]["launch"]
        path = f"M244 {bus_y}H{cols[wave - 1] + 4}V{n(y + chip_h / 2)}H{n(x)}"
        o.append(packet(path, start, start + TRAVEL, c))

    # verify and log panel
    o.append(rect(728, 122, 120, 120, 8, c["chip"], c["line"]))
    o.append(text(740, 142, "verify once", c["text"], 12, font_weight="700"))
    for k, (label, at) in enumerate(
        zip(["ownership", "tests, 1 run", "full diff"], VERIFY_TICKS, strict=True)
    ):
        cy = 166 + k * 24
        o.append(ticked(746, cy, at, c))
        o.append(text(758, cy + 4, label, c["text"], 11))
    o.append(wire("M788 242V258", c))
    o.append(chevron(788, 258, c, down=True))
    o.append(rect(728, 262, 120, 110, 8, c["chip"], c["line"]))
    o.append(text(740, 282, "run log", c["text"], 12, font_weight="700"))
    for k, (label, at) in enumerate(zip(["+6 lines", "stats, hints"], LOG_TICKS, strict=True)):
        cy = 306 + k * 24
        o.append(ticked(746, cy, at, c))
        o.append(text(758, cy + 4, label, c["text"], 11))
    o.append(packet("M700 240H712V182H728", *VERIFY_PACKET, c))
    o.append(packet("M788 242V262", *LOG_PACKET, c))

    # caption strip
    o.append(rect(24, 424, 832, 38, 10, c["panel"]))
    o.append(rect(34, 434, 3, 18, 1.5, c["accent"]))
    o += captions(46, 447, 13, None, c)
    return w, h, o


def phone(c: dict) -> tuple[int, int, list[str]]:
    w, h = 320, 780
    o: list[str] = []
    o.append(
        text(16, 26, "FOREMAN / HOW A TASK RUNS", c["accent"], 10.5, "m", letter_spacing="1.2")
    )
    for i, (kind, label) in enumerate(
        [("queued", "queued"), ("run", "running"), ("warn", "rerun"), ("done", "done")]
    ):
        x = 22 + i * 74
        o.append(badge(kind, x, 42, c))
        o.append(text(x + 10, 46, label, c["muted"], 10.5))

    pill_w = 92
    pos = [(16 + (i % 3) * 98, 58 + (i // 3) * 30) for i in range(len(STEPS))]
    for x, y in pos:
        o.append(rect(x, y, pill_w, 24, 12, c["panel"]))
    stops = [(t, (pos[i][0] - 16, pos[i][1] - 58)) for i, (_, t) in enumerate(STEPS)]
    stops.append((RESET, (0, 0)))
    o.append(
        f'<g>{move(stops)}<rect x="16" y="58" width="{pill_w}" height="24" rx="12" '
        f'fill="{c["accent_fill"]}" stroke="{c["accent"]}" stroke-width="1.6"/></g>'
    )
    for (label, _), (x, y) in zip(STEPS, pos, strict=True):
        o.append(
            text(
                x + pill_w / 2,
                y + 16,
                label,
                c["text"],
                10.5,
                "m",
                text_anchor="middle",
                letter_spacing="0.6",
            )
        )

    o.append(rect(16, 124, 288, 58, 10, c["panel"]))
    o.append(rect(24, 133, 3, 40, 1.5, c["accent"]))
    o += captions(34, 143, 12, 41, c)

    # plan
    o.append(rect(16, 190, 288, 212, 10, c["panel"]))
    o.append(text(26, 208, "PLAN", c["muted"], 10.5, "m", letter_spacing="1.2"))
    o.append(rect(26, 216, 268, 54, 8, c["chip"], c["line"]))
    o.append(text(36, 232, "request", c["muted"], 10.5, "m"))
    for k, line in enumerate(wrap(TASK, 40)):
        o.append(text(36, 249 + k * 14, line, c["text"], 11.5))
    o.append(text(26, 288, "template: feature", c["muted"], 10.5, "m"))
    cells = []
    for k, (sid, kind, _, _) in enumerate(SUBTASKS):
        x, cy = 26 + (k // 3) * 138, 307 + (k % 3) * 22
        cells.append((x, cy))
        o.append(text(x + 8, cy + 4, sid, c["text"], 11, "m"))
        o.append(text(x + 124, cy + 4, kind, c["muted"], 10.5, text_anchor="end"))
    sweep = [(0.0, (0, 0))] + [
        (0.09 + k * 0.013, (cells[k][0] - 26, cells[k][1] - 307)) for k in range(1, 6)
    ]
    first, op = fade([(0.08, 0.18)])
    o.append(
        f'<g opacity="{first}">{op}<g>{move(sweep)}'
        f'<rect x="26" y="297" width="130" height="20" rx="5" fill="{c["accent_fill"]}"/></g></g>'
    )
    gate_y = 368
    o.append(rect(26, gate_y, 268, 26, 8, c["chip"], c["line"]))
    o.append(text(36, gate_y + 17, "plan.py check", c["text"], 11, "m"))
    o += gate_result(284, gate_y + 17, 11, c)

    # route and run
    o.append(rect(16, 410, 288, 222, 10, c["panel"]))
    o.append(text(26, 428, "ROUTE AND RUN", c["muted"], 10.5, "m", letter_spacing="1.2"))
    cols = [80, 152, 224]
    col_w, chip_w, chip_h = 72, 66, 20
    for k, x in enumerate(cols):
        o.append(
            text(x + col_w / 2, 444, f"wave {k + 1}", c["muted"], 10.5, "m", text_anchor="middle")
        )
    lanes = {"haiku": (458, 32), "sonnet": (494, 56), "opus": (554, 34), "fable": (592, 34)}
    for name, (ly, lh) in lanes.items():
        o.append(rect(22, ly, 276, lh, 6, c["lane"]))
        o.append(text(30, ly + lh / 2 + 4, name, c["text"], 12, font_weight="700"))
    bus_y = 452
    for x in cols:
        o.append(wire(f"M{x + 3} {bus_y}V626", c))
    o.append(wire(f"M160 {gate_y + 26}V{bus_y}", c))
    o.append(wire(f"M{cols[0] + 3} {bus_y}H{cols[-1] + 3}", c))
    slot = {}
    stack: dict[tuple[str, int], int] = {}
    for sid, _, tier, wave in SUBTASKS:
        ly, lh = lanes[tier]
        k = stack.get((tier, wave), 0)
        stack[(tier, wave)] = k + 1
        x = cols[wave - 1] + (col_w - chip_w) / 2 + 2
        y = ly + 5 + k * 26 if tier == "sonnet" else ly + (lh - chip_h) / 2
        slot[sid] = (x, y)
    bx, by = slot["build-ui"]
    mid = bx + chip_w / 2
    o.append(wire(f"M{n(mid)} {n(by + chip_h + 1)}V{lanes['opus'][0] + 6}", c, dashed=True))
    o.append(chevron(mid, lanes["opus"][0] + 6, c, down=True))
    o.append(text(mid, lanes["opus"][0] + 19, "failed:", c["muted"], 10.5, text_anchor="middle"))
    o.append(
        text(mid, lanes["opus"][0] + 30, "one tier up", c["muted"], 10.5, text_anchor="middle")
    )
    o += label_on_lane(188, lanes["fable"][0] + 21, "not needed in this plan", c)
    for sid, _, _, _ in SUBTASKS:
        x, y = slot[sid]
        o += chip(sid, x, y, chip_w, chip_h, 10.5, c)
    for sid, _, _, wave in SUBTASKS:
        x, y = slot[sid]
        start = TIMES[sid]["launch"]
        path = f"M160 {gate_y + 26}V{bus_y}H{cols[wave - 1] + 3}V{n(y + chip_h / 2)}H{n(x)}"
        o.append(packet(path, start, start + TRAVEL, c))

    # verify and log
    o.append(rect(16, 640, 288, 130, 10, c["panel"]))
    o.append(text(26, 658, "VERIFY, LOG", c["muted"], 10.5, "m", letter_spacing="1.2"))
    o.append(rect(26, 666, 130, 94, 8, c["chip"], c["line"]))
    o.append(text(36, 684, "verify once", c["text"], 12, font_weight="700"))
    for k, (label, at) in enumerate(
        zip(["ownership", "tests, 1 run", "full diff"], VERIFY_TICKS, strict=True)
    ):
        cy = 704 + k * 20
        o.append(ticked(42, cy, at, c))
        o.append(text(53, cy + 4, label, c["text"], 11))
    o.append(rect(164, 666, 130, 94, 8, c["chip"], c["line"]))
    o.append(text(174, 684, "run log", c["text"], 12, font_weight="700"))
    for k, (label, at) in enumerate(zip(["+6 lines", "stats, hints"], LOG_TICKS, strict=True)):
        cy = 704 + k * 20
        o.append(ticked(180, cy, at, c))
        o.append(text(191, cy + 4, label, c["text"], 11))
    o.append(wire("M156 712H162", c))
    o.append(chevron(161, 712, c))
    o.append(packet(f"M{cols[2] + 3} 626V636H91V666", *VERIFY_PACKET, c))
    o.append(packet("M156 712H164", *LOG_PACKET, c))
    return w, h, o


def captions(x: float, y: float, size: float, width: int | None, c: dict) -> list[str]:
    out = []
    for k, (start, line) in enumerate(CAPTIONS):
        end = CAPTIONS[k + 1][0] if k + 1 < len(CAPTIONS) else RESET
        spans = [(start, end)] if start > 0 else [(0.0, end), (RESET + F, 1.0)]
        first, op = fade(spans)
        if width is None:
            body = text(x, y, line, c["text"], size)
        else:
            body = "".join(
                text(x, y + i * (size + 3), part, c["text"], size)
                for i, part in enumerate(wrap(line, width))
            )
        out.append(f'<g opacity="{first}">{op}{body}</g>')
    return out


def svg(layout, theme: str) -> str:
    c = THEMES[theme]
    w, h, body = layout(c)
    desc = (
        "One foreman dispatch run, step by step. A request comes in and the feature template "
        "splits it into 6 subtasks: map, build-api, build-ui, docs, review and verify. plan.py "
        "check passes the plan with 3 waves before any agent starts. Each subtask goes to an "
        "agent on the model its kind of work needs: wave 1 runs the scout on Haiku; wave 2 runs "
        "two builders on Sonnet in parallel, and build-ui stops short, so it reruns once on "
        "Sonnet at higher effort (a subtask that is wrong after a real try goes one tier up, to "
        "Opus); wave 3 runs docs on Haiku and review and verify on Sonnet. Opus and Fable are "
        "not needed in this plan. The foreman then checks file ownership, runs the tests once "
        "and reads the full diff, and each outcome goes to the run log, which plan.py stats "
        "turns into tune hints."
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-labelledby="{P}-title {P}-desc">\n'
        f'<title id="{P}-title">How foreman runs a task</title>\n'
        f'<desc id="{P}-desc">{escape(desc)}</desc>\n'
        f"<style>.{P}-s{{font-family:{SANS};font-weight:500}}"
        f".{P}-m{{font-family:{MONO};font-weight:600}}</style>\n"
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="{c["bg"]}" '
        f'stroke="{c["line"]}"/>\n' + "\n".join(body) + "\n</svg>\n"
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for layout, suffix in [(desktop, ""), (phone, "-mobile")]:
        for theme in THEMES:
            path = OUT / f"how-it-works-{theme}{suffix}.svg"
            path.write_bytes(svg(layout, theme).encode("utf-8"))
            print(f"wrote {path.relative_to(ROOT).as_posix()} ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

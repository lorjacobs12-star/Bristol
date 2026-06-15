"""
Bristol — fullscreen UI
Orb fills the screen; last exchange overlays at the bottom.
Integrates with assistant.py via shared state in orb.py.
"""
import math
import time
import threading
import textwrap
import numpy as np
import pygame
import orb as _orb

# ── Layout ────────────────────────────────────────────────────────────────────
WIDTH, HEIGHT   = 1280, 720
FPS             = 60
CENTER          = (WIDTH // 2, HEIGHT // 2 - 40)
BASE_RADIUS     = int(min(WIDTH, HEIGHT) * 0.28)
NUM_POINTS      = 240

# Colours
BG              = (6, 3, 14)
OVERLAY_BG      = (12, 6, 28, 200)
COLOR_USER      = (160, 120, 255)
COLOR_JARVIS    = (220, 180, 255)
COLOR_LABEL     = (100, 60, 180)
COLOR_HINT      = (60, 40, 100)
COLOR_INPUT_BG  = (18, 10, 36, 220)
COLOR_INPUT_FG  = (200, 160, 255)
COLOR_CURSOR    = (180, 100, 255)

# ── Shared transcript / input state ──────────────────────────────────────────
_transcript: list[tuple[str, str]] = []   # [("user"|"jarvis", text), ...]
_transcript_lock = threading.Lock()
_input_text   = ""
_input_active = False
_input_lock   = threading.Lock()
_submit_cb    = None                       # callable(text) set by assistant


def add_line(role: str, text: str) -> None:
    with _transcript_lock:
        _transcript.append((role, text))
        if len(_transcript) > 20:
            _transcript.pop(0)


def set_submit_callback(fn) -> None:
    global _submit_cb
    _submit_cb = fn


def get_input_text() -> str:
    with _input_lock:
        return _input_text


# ── Font cache ────────────────────────────────────────────────────────────────
_fonts: dict[int, pygame.font.Font] = {}


def font(size: int) -> pygame.font.Font:
    if size not in _fonts:
        _fonts[size] = pygame.font.SysFont("monospace", size)
    return _fonts[size]


# ── Orb drawing (scaled from orb.py logic) ───────────────────────────────────
def _lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _glow(surface, color, center, radius, layers=8):
    for i in range(layers, 0, -1):
        alpha = int(50 * (i / layers))
        r = radius + (layers - i) * 6
        s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, alpha), (r + 2, r + 2), r)
        surface.blit(s, (center[0] - r - 2, center[1] - r - 2))


def _wave_points(t, amplitude, num_points, base_radius, layer):
    pts = []
    freq = 1.0 + layer * 0.6
    speed = 0.8 + layer * 0.3
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        wave = sum(
            math.sin(angle * b * freq + t * speed * b * 0.4) / b
            for b in range(1, 6)
        ) / 5
        idle = 0.10 * math.sin(t * 1.2 + layer * 1.1)
        r = base_radius + (wave * 36 + idle * base_radius) * (0.25 + amplitude * 0.75)
        pts.append((CENTER[0] + r * math.cos(angle),
                    CENTER[1] + r * math.sin(angle)))
    return pts


def _draw_rings(surface, t, amplitude):
    for i in range(3):
        radius = BASE_RADIUS * (1.3 + i * 0.2) + amplitude * 28
        alpha  = int(35 + 25 * math.sin(t * 0.7 + i) + amplitude * 55)
        alpha  = max(0, min(255, alpha))
        dashes = 56 + i * 10
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for d in range(dashes):
            a0 = 2 * math.pi * d / dashes + t * (0.18 + i * 0.09)
            a1 = a0 + (2 * math.pi / dashes) * 0.55
            pts = [(CENTER[0] + radius * math.cos(a0 + (a1 - a0) * k / 8),
                    CENTER[1] + radius * math.sin(a0 + (a1 - a0) * k / 8))
                   for k in range(9)]
            if len(pts) >= 2:
                pygame.draw.lines(s, (200, 100, 255, alpha), False, pts, 1)
        surface.blit(s, (0, 0))


def _draw_orb(surface, t, amplitude):
    _draw_rings(surface, t, amplitude)

    layers = [
        (BASE_RADIUS * 1.20, (60, 20, 140),  1, 75),
        (BASE_RADIUS * 1.08, (120, 60, 200), 2, 140),
        (BASE_RADIUS * 1.00, (180, 80, 255), 2, 210),
    ]
    for idx, (rad, color, lw, alpha) in enumerate(layers):
        pts = _wave_points(t, amplitude, NUM_POINTS, rad, idx)
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        closed = pts + [pts[0]]
        for j in range(len(closed) - 1):
            pygame.draw.line(s, (*color, alpha), closed[j], closed[j + 1], lw)
        surface.blit(s, (0, 0))

    pulse = 0.07 * math.sin(t * 2.5)
    r = int(BASE_RADIUS * (0.52 + pulse + amplitude * 0.10))
    _glow(surface, (80, 20, 160), CENTER, r + 12)
    for layer in range(r, 0, -3):
        frac = layer / r
        color = _lerp_color((180, 80, 255), (120, 40, 220), 1 - frac)
        alpha = int(170 + 85 * (1 - frac))
        circ = pygame.Surface((layer * 2, layer * 2), pygame.SRCALPHA)
        pygame.draw.circle(circ, (*color, alpha), (layer, layer), layer)
        surface.blit(circ, (CENTER[0] - layer, CENTER[1] - layer))


# ── Overlay: transcript + input bar ──────────────────────────────────────────
OVERLAY_TOP    = HEIGHT - 220
INPUT_H        = 44
INPUT_PAD      = 16
TRANSCRIPT_H   = OVERLAY_TOP - 10


def _draw_overlay(surface, mode):
    # semi-transparent transcript backdrop
    panel = pygame.Surface((WIDTH, HEIGHT - OVERLAY_TOP), pygame.SRCALPHA)
    panel.fill(OVERLAY_BG)
    surface.blit(panel, (0, OVERLAY_TOP))

    # last 4 lines of transcript
    with _transcript_lock:
        lines = list(_transcript[-4:])

    y = OVERLAY_TOP + 12
    for role, text in lines:
        color  = COLOR_USER if role == "user" else COLOR_JARVIS
        prefix = "You" if role == "user" else "BRISTOL"
        label  = font(13).render(prefix, True, COLOR_LABEL)
        surface.blit(label, (INPUT_PAD, y))
        # wrap text
        wrapped = textwrap.wrap(text, width=110)
        for wline in wrapped[:2]:
            txt = font(15).render(wline, True, color)
            surface.blit(txt, (INPUT_PAD + 80, y))
            y += 20
        y += 4

    # input bar
    bar_y = HEIGHT - INPUT_H - 10
    bar = pygame.Surface((WIDTH - INPUT_PAD * 2, INPUT_H), pygame.SRCALPHA)
    bar.fill(COLOR_INPUT_BG)
    surface.blit(bar, (INPUT_PAD, bar_y))

    with _input_lock:
        text = _input_text

    placeholder = "Type a message or press [M] to speak..."
    display = text if text else placeholder
    color   = COLOR_INPUT_FG if text else COLOR_HINT
    txt_surf = font(16).render(display, True, color)
    surface.blit(txt_surf, (INPUT_PAD + 10, bar_y + 13))

    # blinking cursor
    if text and int(time.time() * 2) % 2 == 0:
        cx = INPUT_PAD + 10 + txt_surf.get_width() + 2
        pygame.draw.rect(surface, COLOR_CURSOR, (cx, bar_y + 10, 2, 24))

    # mode chip top-right
    chip_color = {
        "idle":      (100, 60, 180),
        "listening": (180, 80, 255),
        "speaking":  (220, 160, 255),
    }.get(mode, (180, 80, 255))
    label_text = {
        "idle":      "STANDBY",
        "listening": "LISTENING ●",
        "speaking":  "SPEAKING ▶",
    }.get(mode, mode.upper())
    chip = font(13).render(label_text, True, chip_color)
    surface.blit(chip, (WIDTH - chip.get_width() - 20, 18))

    # hint
    hint = font(12).render("[M] mic  [Enter] send  [Esc] quit", True, COLOR_HINT)
    surface.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 14))


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    global _input_text, _input_active

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Bristol")
    clock  = pygame.time.Clock()

    t = 0.0

    while True:
        amplitude, mode = _orb.get_state()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return
                elif event.key == pygame.K_RETURN:
                    with _input_lock:
                        text = _input_text.strip()
                        _input_text = ""
                    if text and _submit_cb:
                        threading.Thread(target=_submit_cb, args=(text,), daemon=True).start()
                elif event.key == pygame.K_BACKSPACE:
                    with _input_lock:
                        _input_text = _input_text[:-1]
                elif event.key == pygame.K_m and not _input_text:
                    if _submit_cb:
                        threading.Thread(target=lambda: _submit_cb(None), daemon=True).start()
                else:
                    with _input_lock:
                        _input_text += event.unicode

        screen.fill(BG)
        _draw_orb(screen, t, amplitude)
        _draw_overlay(screen, mode)
        pygame.display.flip()

        t += 1 / FPS
        clock.tick(FPS)


# ── Standalone demo ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    def _demo():
        msgs = [
            ("user",    "What's the weather like today?"),
            ("jarvis",  "Currently 72°F with partly cloudy skies. A pleasant afternoon."),
            ("user",    "Set a reminder for 5pm."),
            ("jarvis",  "Reminder set for 5:00 PM. I'll notify you when the time comes."),
        ]
        modes = ["idle", "listening", "speaking"]
        for mi, (role, text) in enumerate(msgs):
            _orb.set_mode(modes[mi % len(modes)])
            for i in range(90):
                _orb.set_amplitude(0.3 + 0.5 * math.sin(i * 0.2))
                time.sleep(1 / 60)
            add_line(role, text)
            time.sleep(0.5)
        _orb.set_mode("idle")
        _orb.set_amplitude(0.1)

    import math
    threading.Thread(target=_demo, daemon=True).start()
    run()

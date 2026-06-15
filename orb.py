import math
import time
import threading
import numpy as np
import pygame

# ── Config ────────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 600, 600
FPS = 60
CENTER = (WIDTH // 2, HEIGHT // 2)
BASE_RADIUS = 120
NUM_POINTS = 180

# Purple/violet palette
COLOR_BG        = (8, 4, 18)
COLOR_CORE      = (120, 40, 220)
COLOR_CORE_GLOW = (80, 20, 160)
COLOR_WAVE1     = (180, 80, 255)
COLOR_WAVE2     = (120, 60, 200)
COLOR_WAVE3     = (60, 20, 140)
COLOR_RING      = (200, 100, 255)

# ── State shared with audio thread ────────────────────────────────────────────
_amplitude = 0.0          # 0.0 – 1.0, set by audio callback
_mode = "idle"            # "idle" | "listening" | "speaking"
_lock = threading.Lock()


def set_amplitude(value: float) -> None:
    global _amplitude
    with _lock:
        _amplitude = max(0.0, min(1.0, float(value)))


def set_mode(mode: str) -> None:
    global _mode
    with _lock:
        _mode = mode


def get_state():
    with _lock:
        return _amplitude, _mode


# ── Drawing helpers ───────────────────────────────────────────────────────────
def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_glow_circle(surface, color, center, radius, layers=6):
    for i in range(layers, 0, -1):
        alpha = int(60 * (i / layers))
        r = radius + (layers - i) * 4
        glow = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*color, alpha), (r + 2, r + 2), r)
        surface.blit(glow, (center[0] - r - 2, center[1] - r - 2))


def build_waveform_points(t, amplitude, num_points, base_radius, layer):
    points = []
    freq_scale = 1.0 + layer * 0.6
    speed = 0.8 + layer * 0.3
    noise_bands = 5

    for i in range(num_points):
        angle = (2 * math.pi * i) / num_points
        # layered sine waves for organic feel
        wave = 0.0
        for band in range(1, noise_bands + 1):
            wave += (
                math.sin(angle * band * freq_scale + t * speed * band * 0.4)
                / band
            )
        wave /= noise_bands

        idle_pulse = 0.12 * math.sin(t * 1.2 + layer * 1.1)
        r = base_radius + (wave * 28 + idle_pulse * base_radius) * (0.3 + amplitude * 0.7)
        x = CENTER[0] + r * math.cos(angle)
        y = CENTER[1] + r * math.sin(angle)
        points.append((x, y))
    return points


def draw_wave_layer(surface, points, color, width, alpha=255):
    if len(points) < 3:
        return
    layer_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    closed = points + [points[0]]
    for j in range(len(closed) - 1):
        pygame.draw.line(layer_surf, (*color, alpha), closed[j], closed[j + 1], width)
    surface.blit(layer_surf, (0, 0))


def draw_rotating_rings(surface, t, amplitude, mode):
    num_rings = 3
    for i in range(num_rings):
        radius = BASE_RADIUS * (1.35 + i * 0.22) + amplitude * 20
        alpha = int(40 + 30 * math.sin(t * 0.7 + i) + amplitude * 60)
        alpha = max(0, min(255, alpha))
        dash_count = 48 + i * 8
        dash_on = 0.55
        ring_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for d in range(dash_count):
            a0 = (2 * math.pi * d / dash_count) + t * (0.2 + i * 0.1)
            a1 = a0 + (2 * math.pi / dash_count) * dash_on
            steps = 8
            pts = []
            for s in range(steps + 1):
                a = a0 + (a1 - a0) * s / steps
                x = CENTER[0] + radius * math.cos(a)
                y = CENTER[1] + radius * math.sin(a)
                pts.append((x, y))
            if len(pts) >= 2:
                pygame.draw.lines(ring_surf, (*COLOR_RING, alpha), False, pts, 1)
        surface.blit(ring_surf, (0, 0))


def draw_orb_core(surface, t, amplitude, mode):
    pulse = 0.08 * math.sin(t * 2.5)
    r = int(BASE_RADIUS * (0.55 + pulse + amplitude * 0.12))

    # outer glow
    draw_glow_circle(surface, COLOR_CORE_GLOW, CENTER, r + 10, layers=8)

    # gradient core (draw concentric circles)
    for layer in range(r, 0, -2):
        frac = layer / r
        color = lerp_color(COLOR_WAVE1, COLOR_CORE, 1 - frac)
        alpha = int(180 + 75 * (1 - frac))
        circ = pygame.Surface((layer * 2, layer * 2), pygame.SRCALPHA)
        pygame.draw.circle(circ, (*color, alpha), (layer, layer), layer)
        surface.blit(circ, (CENTER[0] - layer, CENTER[1] - layer))


# ── Main render loop ──────────────────────────────────────────────────────────
def run_orb():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Bristol — Waveform Orb")
    clock = pygame.time.Clock()

    t = 0.0
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        amplitude, mode = get_state()

        screen.fill(COLOR_BG)

        # rotating dashed rings
        draw_rotating_rings(screen, t, amplitude, mode)

        # waveform layers (back to front)
        layers = [
            (BASE_RADIUS * 1.22, COLOR_WAVE3, 1, 80),
            (BASE_RADIUS * 1.10, COLOR_WAVE2, 2, 140),
            (BASE_RADIUS * 1.00, COLOR_WAVE1, 2, 210),
        ]
        for i, (rad, color, lw, alpha) in enumerate(layers):
            pts = build_waveform_points(t, amplitude, NUM_POINTS, rad, i)
            draw_wave_layer(screen, pts, color, lw, alpha)

        # glowing core
        draw_orb_core(screen, t, amplitude, mode)

        # mode label
        font = pygame.font.SysFont("monospace", 14)
        label = {"idle": "STANDBY", "listening": "LISTENING", "speaking": "SPEAKING"}.get(mode, mode.upper())
        color = {"idle": (100, 60, 180), "listening": (180, 80, 255), "speaking": (220, 160, 255)}.get(mode, (180, 80, 255))
        text = font.render(label, True, color)
        screen.blit(text, (CENTER[0] - text.get_width() // 2, CENTER[1] + BASE_RADIUS + 40))

        pygame.display.flip()
        t += 1 / FPS
        clock.tick(FPS)

    pygame.quit()


# ── Demo: auto-animate amplitude when run standalone ─────────────────────────
def _demo_thread():
    modes = ["idle", "listening", "speaking"]
    mi = 0
    while True:
        set_mode(modes[mi % len(modes)])
        mi += 1
        for i in range(120):
            v = 0.5 + 0.5 * math.sin(i * 0.15)
            set_amplitude(v if modes[(mi - 1) % 3] != "idle" else v * 0.2)
            time.sleep(1 / 60)


if __name__ == "__main__":
    threading.Thread(target=_demo_thread, daemon=True).start()
    run_orb()

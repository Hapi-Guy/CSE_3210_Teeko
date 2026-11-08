"""Small widget toolkit in the proposal mockup's style (all geometry in design units)."""

import math

import pygame

from . import theme


def inside(rect, pos) -> bool:
    x, y, w, h = rect
    return x <= pos[0] <= x + w and y <= pos[1] <= y + h


class Widget:
    def __init__(self, rect):
        self.rect = rect
        self.visible = True
        self.enabled = True
        self.hover = False

    def handle(self, event, pos) -> bool:
        return False

    def draw(self, g) -> None:
        pass

    def draw_overlay(self, g) -> None:
        pass

    def _track_hover(self, event, pos):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.enabled and inside(self.rect, pos)


class Button(Widget):
    """Styles: primary (blue), secondary (white/blue outline), amber, ghost, link, danger."""

    def __init__(self, rect, text, on_click=None, style="primary", size=18, weight="semibold",
                 tooltip=None):
        super().__init__(rect)
        self.text = text
        self.on_click = on_click
        self.style = style
        self.size = size
        self.weight = weight
        self.pressed = False
        self.highlight = False
        self.tooltip = tooltip

    def handle(self, event, pos):
        if not self.visible:
            return False
        self._track_hover(event, pos)
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and inside(self.rect, pos):
            self.pressed = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.pressed:
            self.pressed = False
            if inside(self.rect, pos) and self.on_click:
                self.on_click()
            return True
        return False

    def colors(self):
        s = self.style
        if not self.enabled:
            return theme.USED_FILL, theme.USED_BORDER, theme.USED_TEXT
        if s == "primary":
            fill = theme.BLUE_DARK if (self.hover or self.highlight) else theme.BLUE
            return fill, None, theme.WHITE
        if s == "amber":
            fill = theme.AMBER_DARK if self.hover else theme.AMBER
            return fill, theme.AMBER_DARK, theme.NAVY
        if s == "secondary":
            fill = theme.BLUE_PALE if self.hover else theme.WHITE
            return fill, theme.BLUE, theme.NAVY
        if s == "danger":
            fill = (250, 228, 228) if self.hover else theme.WHITE
            return fill, theme.RED, theme.RED_DARK
        if s == "ghost":
            return (theme.BLUE_PALE if self.hover else None), None, theme.NAVY
        return None, None, theme.BLUE_DARK if self.hover else theme.BLUE      # link

    def draw(self, g):
        if not self.visible:
            return
        x, y, w, h = self.rect
        fill, border, text = self.colors()
        dy = 1 if self.pressed else 0
        r = (x, y + dy, w, h)
        radius = min(h / 2, 14)
        if self.style == "primary" and self.enabled:
            g.shadow(r, radius, 3, 30)
        g.round_rect(r, fill, radius, border, 2 if border else 0)
        if self.highlight and self.style == "primary":
            g.round_rect((x - 3, y - 3 + dy, w + 6, h + 6), None, radius + 3, theme.AMBER, 2.5)
        g.text(self.text, (x + w / 2, y + h / 2 + dy), self.size, text, self.weight, "center",
               max_width=w - 10)
        if self.style == "link" and self.hover:
            tw = g.text_width(self.text, self.size, self.weight)
            g.line((x + w / 2 - tw / 2, y + h / 2 + self.size * 0.62),
                   (x + w / 2 + tw / 2, y + h / 2 + self.size * 0.62), text, 1.5)


class Segmented(Widget):
    """Mockup-style toggle: the selected option is filled blue."""

    def __init__(self, rect, options, value, on_change=None, size=15, weight="semibold"):
        super().__init__(rect)
        self.options = list(options)       # [(value, label)]
        self.value = value
        self.on_change = on_change
        self.size = size
        self.weight = weight
        self.hover_index = -1

    def _index_at(self, pos):
        x, y, w, h = self.rect
        if not inside(self.rect, pos):
            return -1
        return min(len(self.options) - 1, int((pos[0] - x) / (w / len(self.options))))

    def handle(self, event, pos):
        if not (self.visible and self.enabled):
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover_index = self._index_at(pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            i = self._index_at(pos)
            if i >= 0:
                value = self.options[i][0]
                if value != self.value:
                    self.value = value
                    if self.on_change:
                        self.on_change(value)
                return True
        return False

    def draw(self, g):
        if not self.visible:
            return
        x, y, w, h = self.rect
        n = len(self.options)
        seg = w / n
        radius = 6
        g.round_rect(self.rect, theme.WHITE, radius, theme.BLUE if self.enabled else theme.USED_BORDER, 2)
        for i, (value, label) in enumerate(self.options):
            sx = x + i * seg
            selected = value == self.value
            if selected:
                g.round_rect((sx + 2, y + 2, seg - 4, h - 4),
                             theme.BLUE if self.enabled else theme.USED_BORDER, radius - 2)
            elif i == self.hover_index and self.enabled:
                g.round_rect((sx + 2, y + 2, seg - 4, h - 4), theme.BLUE_PALE, radius - 2)
            color = theme.WHITE if selected else (theme.NAVY if self.enabled else theme.USED_TEXT)
            g.text(label, (sx + seg / 2, y + h / 2), self.size, color, self.weight, "center",
                   max_width=seg - 6)


class Selector(Widget):
    """◀ value ▶ picker that cycles through options."""

    def __init__(self, rect, options, value, on_change=None, size=15):
        super().__init__(rect)
        self.options = list(options)
        self.value = value
        self.on_change = on_change
        self.size = size
        self.hover_side = 0

    def _shift(self, d):
        values = [v for v, _ in self.options]
        i = values.index(self.value) if self.value in values else 0
        self.value = values[(i + d) % len(values)]
        if self.on_change:
            self.on_change(self.value)

    def handle(self, event, pos):
        if not (self.visible and self.enabled):
            return False
        x, y, w, h = self.rect
        if event.type == pygame.MOUSEMOTION:
            self.hover_side = 0 if not inside(self.rect, pos) else (-1 if pos[0] < x + w / 2 else 1)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and inside(self.rect, pos):
            self._shift(-1 if pos[0] < x + w / 2 else 1)
            return True
        if event.type == pygame.MOUSEWHEEL and inside(self.rect, pos):
            self._shift(-1 if event.y > 0 else 1)
            return True
        return False

    def draw(self, g):
        if not self.visible:
            return
        x, y, w, h = self.rect
        g.round_rect(self.rect, theme.WHITE, 6, theme.BLUE if self.enabled else theme.USED_BORDER, 2)
        label = dict(self.options).get(self.value, str(self.value))
        g.text(label, (x + w / 2, y + h / 2), self.size, theme.NAVY if self.enabled else theme.USED_TEXT,
               "semibold", "center", max_width=w - 40)
        for side, ax in ((-1, x + 13), (1, x + w - 13)):
            col = theme.BLUE_DARK if self.hover_side == side else theme.BLUE
            if not self.enabled:
                col = theme.USED_BORDER
            s = 5
            pts = [(ax + side * s, y + h / 2), (ax - side * s, y + h / 2 - s * 1.2),
                   (ax - side * s, y + h / 2 + s * 1.2)]
            g.triangle(pts, col)


class Slider(Widget):
    def __init__(self, rect, lo, hi, value, on_change=None, step=None, fmt="{:g}", label="",
                 log=False, size=14):
        super().__init__(rect)
        self.lo, self.hi = lo, hi
        self.value = value
        self.on_change = on_change
        self.step = step
        self.fmt = fmt
        self.label = label
        self.log = log
        self.size = size
        self.dragging = False

    def _track(self):
        x, y, w, h = self.rect
        return x + 8, y + h - 10, w - 16

    def _frac(self, v):
        if self.log:
            return (math.log(v) - math.log(self.lo)) / (math.log(self.hi) - math.log(self.lo))
        return (v - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0

    def _value_at(self, px):
        tx, _, tw = self._track()
        f = min(1.0, max(0.0, (px - tx) / tw))
        if self.log:
            v = math.exp(math.log(self.lo) + f * (math.log(self.hi) - math.log(self.lo)))
        else:
            v = self.lo + f * (self.hi - self.lo)
        if self.step:
            v = round(v / self.step) * self.step
        return min(self.hi, max(self.lo, v))

    def _set(self, v):
        if v != self.value:
            self.value = v
            if self.on_change:
                self.on_change(v)

    def handle(self, event, pos):
        if not (self.visible and self.enabled):
            return False
        self._track_hover(event, pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and inside(self.rect, pos):
            self.dragging = True
            self._set(self._value_at(pos[0]))
            return True
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self._set(self._value_at(pos[0]))
            return True
        if event.type == pygame.MOUSEBUTTONUP and self.dragging:
            self.dragging = False
            return True
        return False

    def draw(self, g):
        if not self.visible:
            return
        x, y, w, h = self.rect
        if self.label:
            g.text(self.label, (x, y), self.size, theme.GREY_LABEL, "medium")
        g.text(self.fmt.format(self.value), (x + w, y), self.size, theme.NAVY, "semibold", "topright")
        tx, ty, tw = self._track()
        g.round_rect((tx, ty - 3, tw, 6), theme.BLUE_LINE, 3)
        f = self._frac(self.value)
        g.round_rect((tx, ty - 3, tw * f, 6), theme.BLUE if self.enabled else theme.USED_BORDER, 3)
        g.circle((tx + tw * f, ty), 8 if (self.hover or self.dragging) else 7, theme.WHITE)
        g.circle((tx + tw * f, ty), 8 if (self.hover or self.dragging) else 7,
                 theme.BLUE if self.enabled else theme.USED_BORDER, 2.5)


class Checkbox(Widget):
    def __init__(self, rect, label, value, on_change=None, size=15):
        super().__init__(rect)
        self.label = label
        self.value = value
        self.on_change = on_change
        self.size = size

    def handle(self, event, pos):
        if not (self.visible and self.enabled):
            return False
        self._track_hover(event, pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and inside(self.rect, pos):
            self.value = not self.value
            if self.on_change:
                self.on_change(self.value)
            return True
        return False

    def draw(self, g):
        if not self.visible:
            return
        x, y, w, h = self.rect
        box = (x, y + h / 2 - 10, 20, 20)
        g.round_rect(box, theme.BLUE if self.value else theme.WHITE, 5,
                     theme.BLUE if (self.value or self.hover) else theme.BLUE_LINE, 2)
        if self.value:
            bx, by = x + 4.5, y + h / 2
            g.line((bx, by), (bx + 4.5, by + 4.5), theme.WHITE, 2.5)
            g.line((bx + 4.5, by + 4.5), (bx + 11.5, by - 5), theme.WHITE, 2.5)
        g.text(self.label, (x + 28, y + h / 2), self.size, theme.NAVY if self.enabled else theme.USED_TEXT,
               "medium", "midleft")


class Stepper(Widget):
    """label  [−] value [+]"""

    def __init__(self, rect, label, value, lo, hi, step=1, on_change=None, fmt="{}", size=15):
        super().__init__(rect)
        self.label = label
        self.value = value
        self.lo, self.hi, self.step = lo, hi, step
        self.on_change = on_change
        self.fmt = fmt
        self.size = size
        self.hover_btn = 0

    def _buttons(self):
        x, y, w, h = self.rect
        b = h
        return (x + w - 3 * b - 8, y, b, h), (x + w - b, y, b, h)

    def handle(self, event, pos):
        if not (self.visible and self.enabled):
            return False
        minus, plus = self._buttons()
        if event.type == pygame.MOUSEMOTION:
            self.hover_btn = -1 if inside(minus, pos) else (1 if inside(plus, pos) else 0)
        delta = 0
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            delta = -1 if inside(minus, pos) else (1 if inside(plus, pos) else 0)
        if event.type == pygame.MOUSEWHEEL and inside(self.rect, pos):
            delta = 1 if event.y > 0 else -1
        if delta:
            v = min(self.hi, max(self.lo, self.value + delta * self.step))
            if v != self.value:
                self.value = v
                if self.on_change:
                    self.on_change(v)
            return True
        return False

    def draw(self, g):
        if not self.visible:
            return
        x, y, w, h = self.rect
        g.text(self.label, (x, y + h / 2), self.size, theme.GREY_LABEL, "medium", "midleft")
        minus, plus = self._buttons()
        for r, sign, side in ((minus, "−", -1), (plus, "+", 1)):
            g.round_rect(r, theme.BLUE_PALE if self.hover_btn == side else theme.WHITE, 6, theme.BLUE, 2)
            g.text(sign, (r[0] + r[2] / 2, r[1] + r[3] / 2 - 1), self.size + 3, theme.BLUE, "semibold",
                   "center")
        mid = (minus[0] + minus[2] + plus[0]) / 2
        g.text(self.fmt.format(self.value), (mid, y + h / 2), self.size + 1, theme.NAVY, "semibold",
               "center")


class Dropdown(Widget):
    """The mockup's 'Play Type' box: white with a blue outline and a ▼ marker."""

    def __init__(self, rect, options, value, on_change=None, size=17):
        super().__init__(rect)
        self.options = list(options)
        self.value = value
        self.on_change = on_change
        self.size = size
        self.open = False
        self.hover_index = -1

    def _option_rect(self, i):
        x, y, w, h = self.rect
        return (x, y + h + 4 + i * (h - 4), w, h - 4)

    def handle(self, event, pos):
        if not (self.visible and self.enabled):
            return False
        self._track_hover(event, pos)
        if self.open:
            if event.type == pygame.MOUSEMOTION:
                self.hover_index = next((i for i in range(len(self.options))
                                         if inside(self._option_rect(i), pos)), -1)
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, (value, _) in enumerate(self.options):
                    if inside(self._option_rect(i), pos):
                        self.open = False
                        if value != self.value:
                            self.value = value
                            if self.on_change:
                                self.on_change(value)
                        return True
                self.open = False
                return True
            return event.type in (pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and inside(self.rect, pos):
            self.open = True
            return True
        return False

    def draw(self, g):
        if not self.visible:
            return
        x, y, w, h = self.rect
        g.round_rect(self.rect, theme.BLUE_PALE if self.hover else theme.WHITE, 10, theme.BLUE, 2.2)
        g.text(dict(self.options).get(self.value, ""), (x + 18, y + h / 2), self.size, theme.NAVY,
               "medium", "midleft")
        ax, ay = x + w - 26, y + h / 2
        g.triangle([(ax - 9, ay - 5), (ax + 9, ay - 5), (ax, ay + 6)], theme.BLUE)

    def draw_overlay(self, g):
        if not (self.visible and self.open):
            return
        x, y, w, h = self.rect
        n = len(self.options)
        panel = (x, y + h + 2, w, n * (h - 4) + 4)
        g.shadow(panel, 10, 4, 45)
        g.round_rect(panel, theme.WHITE, 10, theme.BLUE, 2)
        for i, (value, label) in enumerate(self.options):
            r = self._option_rect(i)
            if i == self.hover_index:
                g.round_rect((r[0] + 4, r[1] + 2, r[2] - 8, r[3] - 4), theme.BLUE_PALE, 8)
            g.text(label, (r[0] + 18, r[1] + r[3] / 2), self.size - 1,
                   theme.BLUE_DARK if value == self.value else theme.NAVY,
                   "semibold" if value == self.value else "medium", "midleft")


class Card:
    """White rounded panel with an optional small-caps section label (mockup style)."""

    @staticmethod
    def draw(g, rect, label=None, fill=theme.WHITE, border=theme.BLUE_LINE, radius=12, width=2):
        g.round_rect(rect, fill, radius, border, width)
        if label:
            g.text(label, (rect[0] + 16, rect[1] + 12), 13, theme.GREY_LABEL, "semibold")


def spinner(g, center, radius, t, color=theme.BLUE, width=3):
    """Rotating arc used for 'AI is thinking'."""
    start = t * 5.0
    pts = []
    for i in range(22):
        a = start + i * (math.pi * 1.4 / 21)
        pts.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    for a, b in zip(pts, pts[1:]):
        g.line(a, b, color, width)

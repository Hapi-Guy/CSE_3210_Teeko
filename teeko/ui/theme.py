"""Visual language taken from the project proposal slides (Teeko_AI_Lab.pdf)."""

import os

DESIGN_W, DESIGN_H = 1280, 720          # all layout is in these units, scaled to the window

APP_TITLE = "Teeko AI"
COURSE_LABEL = "CSE 3210 - Artificial Intelligence Lab"
TEAM = (("Sumaiya Afrin Eva", "Roll: 2207039"),
        ("Md. Shomik Shahriar", "Roll: 2207041"))

# --- palette --------------------------------------------------------------
WHITE = (255, 255, 255)
BLUE = (69, 150, 224)            # header bars, primary buttons (#4596E0)
BLUE_DARK = (44, 118, 196)
BLUE_LIGHT = (187, 221, 251)     # checkerboard squares (#BBDDFB)
BLUE_PALE = (232, 243, 253)      # board and info fills (#E8F3FD)
BLUE_LINE = (176, 208, 240)      # soft card borders
NAVY = (31, 58, 95)              # main text (#1F3A5F)
GREY_TEXT = (104, 120, 142)
GREY_LABEL = (88, 104, 126)
GRID = (150, 172, 202)
GRID_DIAG = (190, 207, 229)
POINT = (124, 150, 184)
SHADOW = (20, 50, 90)

RED = (229, 57, 53)              # P1 pieces
RED_DARK = (178, 34, 34)
BLUE_PIECE = (30, 95, 216)       # P2 pieces
BLUE_PIECE_DARK = (16, 60, 150)
PIECE_COLORS = ((RED, RED_DARK), (BLUE_PIECE, BLUE_PIECE_DARK))
PLAYER_COLORS = (RED, BLUE_PIECE)

AMBER = (255, 179, 0)            # selection, targets, Available (#FFB300)
AMBER_DARK = (214, 146, 0)
AMBER_PALE = (255, 243, 205)
USED_FILL = (221, 227, 234)
USED_BORDER = (166, 177, 191)
USED_TEXT = (136, 148, 164)
GREEN = (46, 160, 90)

# --- fonts -----------------------------------------------------------------
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                      "assets")
FONT_FILES = {
    "regular": os.path.join(ASSETS, "fonts", "Fredoka-Regular.ttf"),
    "medium": os.path.join(ASSETS, "fonts", "Fredoka-Medium.ttf"),
    "semibold": os.path.join(ASSETS, "fonts", "Fredoka-SemiBold.ttf"),
    "bold": os.path.join(ASSETS, "fonts", "Fredoka-Bold.ttf"),
}
FALLBACK_FONTS = ("segoeui", "segoeuisymbol", "arial", "dejavusans")

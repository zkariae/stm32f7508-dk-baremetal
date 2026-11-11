"""Theme of the TUI: light grey and blue, in the style of the dialog(1) boxes.

The colours of the classic text dialogs: black text on light grey, blue
frames, titles and selection bar with white text, a blue footer with its
keys in yellow, red for errors. app.py registers HIL_DIALOG and selects it at launch;
the command palette (ctrl+p) still offers the built-in Textual themes.

Every pair of text and background colours used here keeps a contrast ratio
of at least 4.5:1 (WCAG AA), so the TUI stays readable in the VS Code
terminal: contrast() computes it and the checks of this theme use it.

Not reproduced from dialog(1): the red hot letter of each list item (the
tree and the command list have no letter keys) and the shadow of the boxes.

Version: 1.0
Date: 11/11/2026
Author: Z. BEN-AKKA
History:
  1.0  11/11/2026  Initial version.
"""

from textual.theme import Theme

NAME = "hil-dialog"

BLUE = "#0000AA"  # Frames, titles, selection bar: the blue of dialog(1)
RED = "#990000"  # Errors, accent: the red of dialog(1), a shade darker for 4.5:1 on the grey
GREY = "#C0C0C0"  # Screen background
LIGHT_GREY = "#D4D4D4"  # Fields and panes, a little lighter than the screen
DARK_GREY = "#A8A8A8"  # Panels, blurred frames
BLACK = "#000000"
WHITE = "#FFFFFF"
GREEN = "#005000"  # Success: dark, readable on the grey
YELLOW = "#5C4400"  # Warning: dark ochre, a pure yellow is unreadable on the grey

HIL_DIALOG = Theme(
    name=NAME,
    primary=BLUE,
    secondary=BLUE,
    accent=RED,
    warning=YELLOW,
    error=RED,
    success=GREEN,
    foreground=BLACK,
    background=GREY,
    surface=LIGHT_GREY,
    panel=DARK_GREY,
    dark=False,
    variables={
        "block-cursor-background": BLUE,  # Selection bar of the tree and the lists
        "block-cursor-foreground": WHITE,
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": DARK_GREY,
        "block-cursor-blurred-foreground": BLACK,
        "border": BLUE,
        "border-blurred": DARK_GREY,
        "input-selection-background": f"{BLUE} 35%",
        "footer-background": BLUE,
        "footer-foreground": WHITE,
        "footer-description-foreground": WHITE,
        "footer-key-foreground": "#FFFF55",  # Bright yellow on blue, as the keys of a dialog footer
        "footer-key-background": BLUE,
        "button-foreground": BLACK,
        "scrollbar": BLUE,
        "scrollbar-background": DARK_GREY,
    },
)

# (text, background) pairs the screens use; each must reach MIN_CONTRAST
PAIRS = {
    "text on screen": (BLACK, GREY),
    "text in a field": (BLACK, LIGHT_GREY),
    "text on a panel": (BLACK, DARK_GREY),
    "selection bar": (WHITE, BLUE),
    "frame on screen": (BLUE, GREY),
    "error on screen": (RED, GREY),
    "warning on screen": (YELLOW, GREY),
    "success on screen": (GREEN, GREY),
    "footer key": ("#FFFF55", BLUE),
    "footer text": (WHITE, BLUE),
}
MIN_CONTRAST = 4.5


def _luminance(colour: str) -> float:
    """Relative luminance of #RRGGBB (WCAG 2)."""
    channels = [int(colour[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(text: str, background: str) -> float:
    """WCAG contrast ratio of two #RRGGBB colours, from 1 to 21."""
    light, dark = sorted((_luminance(text), _luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)

"""ESS celestial palette. Deep space, gold starlight, restrained."""

SPACE = "#0b0f1e"       # deep-space background
PANEL = "#121831"       # slightly lifted panel fill
EDGE = "#b8894a"        # brass/gold border
GOLD = "#ffd76a"        # starlight accent
GOLD_DIM = "#e8c15a"
SILVER = "#c0c8e0"
SLATE = "#9aa7d0"
RING = "#243049"        # faint orbit line
TEXT = "#cdd6f4"

# severity -> color, for the drift board
SEV = {
    "OK": "#7fd1a0",
    "INFO": "#9aa7d0",
    "WARN": "#e8c15a",
    "DRIFT": "#ff9f6a",
    "FAIL": "#ff6a8a",
}

CSS = f"""
Screen {{
    background: {SPACE};
    color: {TEXT};
}}
Header {{
    background: {SPACE};
    color: {GOLD};
}}
Footer {{
    background: {SPACE};
    color: {SLATE};
}}
#body {{
    height: 1fr;
}}
#orrery {{
    width: 42%;
    border: round {EDGE};
    background: {SPACE};
    content-align: center middle;
}}
#right {{
    width: 58%;
}}
#context {{
    height: auto;
    min-height: 7;
    border: round {EDGE};
    background: {PANEL};
    padding: 0 1;
}}
#drift {{
    height: 1fr;
    border: round {EDGE};
    background: {PANEL};
    padding: 0 1;
}}
.title {{
    color: {GOLD};
    text-style: bold;
}}
"""

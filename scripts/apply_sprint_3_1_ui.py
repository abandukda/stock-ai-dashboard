
"""
Apply Sprint 3.1 UI wiring to app.py.

Run from project root:
python3 scripts/apply_sprint_3_1_ui.py
"""

from pathlib import Path
import re

p = Path("app.py")
text = p.read_text()
backup = Path("app.py.sprint_3_1_backup")
if not backup.exists():
    backup.write_text(text)

def ensure_import(src: str, line: str) -> str:
    if line in src:
        return src
    m = re.search(r"^import streamlit as st\s*$", src, flags=re.MULTILINE)
    if m:
        return src[:m.end()] + "\n" + line + src[m.end():]
    return line + "\n" + src

text = ensure_import(text, "from ui.layout import inject_css")
text = ensure_import(text, "from ui.atlas_dashboard import render_professional_home_header")

if "inject_css()" not in text:
    pattern = r"(st\.set_page_config\([\s\S]*?\n\))"
    text, n = re.subn(pattern, r"\1\n\ninject_css()", text, count=1)
    if n == 0:
        print("Could not find st.set_page_config block. Import added only.")

p.write_text(text)
print("Sprint 3.1 app wiring complete. Backup: app.py.sprint_3_1_backup")

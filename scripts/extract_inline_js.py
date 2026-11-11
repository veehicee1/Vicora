"""Extract inline scripts from the shipped web pages for Node syntax checks."""
from pathlib import Path
import re

OUT = Path("js-check")
OUT.mkdir(exist_ok=True)

for page in ("admin", "student"):
    source = Path("web") / f"{page}.html"
    html = source.read_text(encoding="utf-8")
    blocks = re.findall(r"<script\b[^>]*>(.*?)</script\s*>", html, flags=re.I | re.S)
    inline = [block.strip() for block in blocks if block.strip()]
    if not inline:
        raise SystemExit(f"No inline JavaScript found in {source}")
    target = OUT / f"{page}.js"
    target.write_text("\n;\n".join(inline) + "\n", encoding="utf-8")
    print(f"Extracted {len(inline)} inline script block(s) from {source} to {target}")

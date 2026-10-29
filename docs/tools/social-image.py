"""Makes docs/assets/social.png, the picture shown when a docs link is pasted into
Facebook, Discord, Slack and the like (the og:image in _layouts/default.html).

Built from assets/img/hero.webp, so run it after capture.py (build-media.sh
does). Needs Playwright, like capture.py.
"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parents[1]
HERO = DOCS / "assets" / "img" / "hero.webp"
MARK = DOCS / "assets" / "mark.svg"
OUT = DOCS / "assets" / "social.png"

HTML = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@600&family=Inter+Tight:wght@500&display=swap" rel="stylesheet">
<style>
  html, body { margin: 0; }
  body { width: 1200px; height: 630px; overflow: hidden; background: #1f2933; color: #fff; position: relative; }
  .brand { position: absolute; left: 64px; top: 52px; display: flex; align-items: center; gap: 16px;
           font: 600 34px Oswald, sans-serif; letter-spacing: 0.05em; text-transform: uppercase; }
  .brand img { width: 46px; height: 46px; }
  h1 { position: absolute; left: 64px; top: 106px; margin: 0; font: 600 54px/1.1 Oswald, sans-serif;
       text-transform: uppercase; letter-spacing: 0.01em; }
  p { position: absolute; left: 66px; top: 176px; margin: 0; font: 500 26px "Inter Tight", sans-serif; color: #cfd6db; }
  .shot { position: absolute; left: 50%; bottom: -40px; transform: translateX(-50%); width: 960px;
          padding: 18px 18px 0; background: #e9ecee; border-radius: 16px 16px 0 0; }
  .shot img { display: block; width: 100%; }
</style></head><body>
  <div class="brand"><img src="MARK" alt="">Next Up</div>
  <h1>Walk-in check-in for barber shops</h1>
  <p>Tablet at the door, queue on the TV, barbers call people up from their phones.</p>
  <div class="shot"><img src="HERO" alt=""></div>
</body></html>"""


def main():
    html = HTML.replace("HERO", HERO.as_uri()).replace("MARK", MARK.as_uri())
    with sync_playwright() as playwright:
        executable = os.environ.get("CHROMIUM_PATH")
        browser = playwright.chromium.launch(executable_path=executable) if executable else playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630})
        # A file:// page, so the local pictures load; set_content alone would block them.
        source = DOCS / "tools" / ".social.html"
        source.write_text(html)
        try:
            page.goto(source.as_uri())
            page.wait_for_load_state("networkidle")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(OUT))
        finally:
            source.unlink()
        browser.close()
    print(f"  {OUT.relative_to(DOCS)}  {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()

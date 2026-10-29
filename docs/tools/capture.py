"""Takes the documentation screenshots and records the demo video.

Run by build-media.sh, which starts a throwaway copy of the app for each phase:

  fresh  a new install: the first-run setup page and the Getting Started checklist
  demo   the made-up shop from `flask seed-demo`: every other screenshot, the
         video, and (last, because it changes the look) the branding examples

Screenshots are saved as WebP in docs/assets/img, the video as WebM in
docs/assets/video (build-media.sh converts it to MP4).
"""
import argparse
import io
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parents[1]
IMG = DOCS / "assets" / "img"
VIDEO = DOCS / "assets" / "video"
PASSWORD = "demo-password"

DESKTOP = {"width": 1280, "height": 900}
TABLET = {"width": 820, "height": 1180}
PHONE = {"width": 390, "height": 844}
TV = {"width": 1920, "height": 1080}


def save(png, name, max_width=1800, max_height=None):
    """PNG bytes -> docs/assets/img/<name>.webp, scaled down if very wide and
    cut off at max_height (in final pixels) if given."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if image.width > max_width:
        image = image.resize((max_width, round(image.height * max_width / image.width)), Image.Resampling.LANCZOS)
    if max_height and image.height > max_height:
        image = image.crop((0, 0, image.width, max_height))
    IMG.mkdir(parents=True, exist_ok=True)
    path = IMG / f"{name}.webp"
    image.save(path, "WEBP", quality=84, method=6)
    print(f"  {path.relative_to(DOCS)}  {image.width}x{image.height}  {path.stat().st_size // 1024} KB")


class Capture:
    def __init__(self, playwright, base):
        self.base = base.rstrip("/")
        executable = os.environ.get("CHROMIUM_PATH")
        self.browser = playwright.chromium.launch(executable_path=executable) if executable else playwright.chromium.launch()

    def context(self, viewport, scale=2, **options):
        # en-GB: day-month dates and 24-hour time pickers, like the app's own text.
        return self.browser.new_context(viewport=viewport, device_scale_factor=scale, locale="en-GB", **options)

    def open(self, context, path, wait=900):
        page = context.new_page()
        page.goto(self.base + path)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(wait)  # page fade-in and the live connection
        return page

    def login(self, context, username):
        page = self.open(context, "/login", wait=0)
        page.fill("#username", username)
        page.fill("#password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        return page

    def tall(self, page, width=None):
        """The page body is the scroll area, so make the window as tall as the
        content to capture all of it."""
        height = page.evaluate("document.body.scrollHeight")
        page.set_viewport_size({"width": width or page.viewport_size["width"], "height": height})
        page.wait_for_timeout(300)

    def device_links(self, page):
        page.goto(self.base + "/admin/#device-links")
        # Shown as full URLs; just the paths are needed.
        kiosk = urlparse(page.locator("a[href*='/kiosk/']").first.get_attribute("href")).path
        tv = urlparse(page.locator("a[href*='/display/']").first.get_attribute("href")).path
        return kiosk, tv


# Fresh install -------------------------------------------------------------------


def fresh(cap):
    print("Fresh install")
    context = cap.context(DESKTOP)
    page = cap.open(context, "/")
    save(page.locator(".card").screenshot(), "setup")

    page.fill("#name", "Dana Wells")
    page.fill("#username", "dana")
    page.fill("#password", PASSWORD)
    page.fill("#confirm_password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(900)
    save(page.locator(".setup-card").screenshot(), "getting-started")
    context.close()


# Demo shop -----------------------------------------------------------------------


def demo(cap, video=True):
    print("Demo shop")
    admin = cap.context(DESKTOP)
    admin_page = cap.login(admin, "dana")
    kiosk_url, tv_url = cap.device_links(admin_page)
    location = "/staff/harbour-lane"

    # The TV and the staff dashboard, before anything changes the queue.
    tv = cap.context(TV, scale=1)
    save(cap.open(tv, tv_url, wait=1500).screenshot(), "tv")

    staff = cap.context(DESKTOP)
    staff_page = cap.login(staff, "marco")
    staff_page.goto(cap.base + location)
    staff_page.wait_for_timeout(1200)
    cap.tall(staff_page)
    save(staff_page.screenshot(), "staff-dashboard")
    save(staff_page.locator("#recent-card").screenshot(), "staff-recent")
    save(staff_page.locator("#store-card").screenshot(), "staff-store-card")
    save(staff_page.locator(".announcement-card").screenshot(), "staff-announcement")
    save(staff_page.locator("#break-card").screenshot(), "staff-break")

    phone = cap.context(PHONE, scale=3, is_mobile=True, has_touch=True)
    phone_page = cap.login(phone, "priya")
    save(phone_page.screenshot(), "choose-location")
    phone_page.click("button:has-text('Harbour Lane')")
    phone_page.wait_for_timeout(1200)
    save(phone_page.screenshot(), "staff-phone", max_width=1170)

    # Kiosk.
    tablet = cap.context(TABLET, has_touch=True)
    kiosk = cap.open(tablet, kiosk_url, wait=1200)
    save(kiosk.screenshot(), "kiosk")
    kiosk.fill("#customer_name", "Alex Morgan")
    kiosk.click("#add-person")
    kiosk.locator("#group-people input").last.fill("Charlie Morgan")
    kiosk.click("label.barber-chip:has-text('Priya')")
    kiosk.wait_for_timeout(300)
    save(kiosk.screenshot(), "kiosk-group")
    kiosk.click("button[type=submit]:has-text('Check In')")
    kiosk.wait_for_load_state("networkidle")
    kiosk.wait_for_timeout(1500)
    save(kiosk.screenshot(), "kiosk-confirmation")

    # Admin pages.
    for tab in ("locations", "device-links", "barbers", "settings", "activity"):
        admin_page.set_viewport_size(DESKTOP)
        admin_page.goto(cap.base + "/admin/#" + tab)
        admin_page.reload()
        admin_page.wait_for_timeout(1200 if tab == "device-links" else 700)
        cap.tall(admin_page)
        panel = admin_page.locator(f'[data-tab-panel="{tab}"]')
        save(panel.screenshot(), f"admin-{tab}", max_height=1500 if tab == "activity" else None)
    admin_page.set_viewport_size(DESKTOP)
    admin_page.goto(cap.base + "/admin/")
    admin_page.click("a.btn:has-text('Opening Hours') >> nth=1")
    admin_page.wait_for_timeout(700)
    cap.tall(admin_page)
    save(admin_page.locator("main .card").first.screenshot(), "location-hours")
    save(admin_page.locator("#special-hours").screenshot(), "special-hours", max_height=900)

    admin_page.set_viewport_size(DESKTOP)
    admin_page.goto(cap.base + "/admin/metrics?days=30")
    admin_page.wait_for_timeout(1500)
    cap.tall(admin_page)
    admin_page.wait_for_timeout(800)  # charts redraw at the new size
    save(admin_page.screenshot(), "metrics", max_width=1280)
    save(admin_page.locator(".heatmap-card").screenshot(), "metrics-heatmap")

    if video:
        record_video(cap, kiosk_url, tv_url, location)

    # A closed store, as the kiosk shows it.
    staff_page.set_viewport_size(DESKTOP)
    staff_page.goto(cap.base + location)
    staff_page.wait_for_timeout(800)
    staff_page.click("#store-card button[type=submit]")
    _confirm(staff_page)
    kiosk.reload()
    kiosk.wait_for_timeout(1200)
    save(kiosk.screenshot(), "kiosk-closed")
    staff_page.goto(cap.base + location)
    staff_page.wait_for_timeout(800)
    staff_page.click("#store-card button[type=submit]")
    _confirm(staff_page)

    branding_examples(cap, admin_page, kiosk_url, tv_url)
    for context in (admin, tv, staff, phone, tablet):
        context.close()


def _confirm(page):
    """Accept the app's own confirm dialog if one opens."""
    page.wait_for_timeout(400)
    button = page.locator("#confirm-modal-overlay.open .modal-confirm")
    if button.count():
        button.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)


# Branding ------------------------------------------------------------------------

LOGO_HTML = """
<html><head>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap" rel="stylesheet">
<style>
  body { margin: 0; background: transparent; }
  #logo { display: inline-flex; flex-direction: column; align-items: center; padding: 6px 10px;
          font-family: Oswald, sans-serif; color: #fff; text-transform: uppercase; }
  .big { font-size: 64px; font-weight: 700; letter-spacing: 0.08em; line-height: 1; }
  .small { margin-top: 8px; font-size: 20px; font-weight: 500; letter-spacing: 0.6em; color: #f2b46d; }
  #icon { width: 512px; height: 512px; display: flex; align-items: center; justify-content: center;
          background: #1d2b3a; font-family: Oswald, sans-serif; font-weight: 700; font-size: 230px;
          color: #fff; letter-spacing: 0.02em; }
  #icon span { color: #f2b46d; }
</style></head>
<body><div id="logo"><div class="big">Harbour Lane</div><div class="small">Barbers</div></div>
<div id="icon">H<span>L</span></div></body></html>
"""


def branding_examples(cap, admin_page, kiosk_url, tv_url):
    print("Branding")
    maker = cap.browser.new_page(device_scale_factor=2)
    maker.set_content(LOGO_HTML)
    maker.wait_for_load_state("networkidle")
    maker.evaluate("document.fonts.ready")
    with tempfile.TemporaryDirectory() as tmp:
        logo, icon = Path(tmp, "logo.png"), Path(tmp, "icon.png")
        logo.write_bytes(maker.locator("#logo").screenshot(omit_background=True))
        icon.write_bytes(maker.locator("#icon").screenshot())
        maker.close()

        admin_page.set_viewport_size(DESKTOP)
        admin_page.goto(cap.base + "/admin/#branding")
        admin_page.reload()
        admin_page.fill("#brand-dark", "#1d2b3a")
        admin_page.fill("#brand-accent", "#b45309")
        admin_page.click("#branding-form button[type=submit]")
        admin_page.wait_for_load_state("networkidle")
        for kind, path in (("logo", logo), ("icon", icon)):
            admin_page.goto(cap.base + "/admin/#branding")
            admin_page.locator(f"form[action$='/branding/{kind}'] input[type=file]").set_input_files(str(path))
            admin_page.click(f"form[action$='/branding/{kind}'] button[type=submit]")
            admin_page.wait_for_load_state("networkidle")

    admin_page.goto(cap.base + "/admin/#branding")
    admin_page.reload()
    admin_page.wait_for_timeout(900)
    cap.tall(admin_page)
    save(admin_page.locator('[data-tab-panel="branding"]').screenshot(), "admin-branding")

    tablet = cap.context(TABLET)
    save(cap.open(tablet, kiosk_url, wait=1200).screenshot(), "kiosk-branded")
    tv = cap.context(TV, scale=1)
    save(cap.open(tv, tv_url, wait=1500).screenshot(), "tv-branded")
    tablet.close()
    tv.close()


# Video ---------------------------------------------------------------------------
# One page showing the TV, the kiosk tablet and a barber's phone side by side, each
# a scaled-down frame of the real page. It's served from the app's own address
# (intercepted, never reaching the app) so the frames share the barber's login.

STAGE_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600&family=Inter+Tight:wght@400;500&display=swap" rel="stylesheet">
<style>
  html, body { margin: 0; height: 100%; }
  body { background: #e9ecee; font-family: "Inter Tight", sans-serif; color: #1f2933; overflow: hidden; }
  .devices { position: absolute; top: 175px; left: 0; right: 0; display: flex; justify-content: center;
             align-items: flex-start; gap: 44px; }
  .device { display: flex; flex-direction: column; align-items: center; gap: 14px; }
  .label { font-family: Oswald, sans-serif; text-transform: uppercase; letter-spacing: 0.12em; font-size: 20px;
           color: #52606d; }
  .bezel { background: #111; padding: 12px; border-radius: 22px; box-shadow: 0 18px 40px rgba(0,0,0,.25); }
  .bezel.tv { border-radius: 8px; padding: 10px; }
  .bezel.phone { border-radius: 38px; padding: 12px; }
  .screen { overflow: hidden; border-radius: 12px; background: #fff; }
  .tv .screen { border-radius: 2px; }
  .phone .screen { border-radius: 28px; }
  iframe { border: 0; transform-origin: 0 0; display: block; }
  .caption { position: absolute; left: 0; right: 0; bottom: 70px; text-align: center; font-size: 34px;
             font-weight: 500; transition: opacity .3s; }
  .title { position: absolute; top: 46px; left: 0; right: 0; text-align: center; font-family: Oswald, sans-serif;
           font-size: 44px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
</style></head><body>
<div class="title">A walk-in, from the door to the chair</div>
<div class="devices">
  <div class="device"><div class="bezel phone"><div class="screen" style="width:304px;height:658px">
    <iframe id="phone" src="PHONE_URL" style="width:390px;height:844px;transform:scale(0.78)"></iframe></div></div>
    <div class="label">Barber's phone</div></div>
  <div class="device"><div class="bezel tv"><div class="screen" style="width:960px;height:540px">
    <iframe id="tv" src="TV_URL" style="width:1920px;height:1080px;transform:scale(0.5)"></iframe></div></div>
    <div class="label">TV in the shop</div></div>
  <div class="device"><div class="bezel"><div class="screen" style="width:476px;height:684px">
    <iframe id="kiosk" src="KIOSK_URL" style="width:820px;height:1180px;transform:scale(0.58)"></iframe></div></div>
    <div class="label">Check-in tablet</div></div>
</div>
<div class="caption" id="caption"></div>
</body></html>
"""

TAP_JS = """
el => {
  const r = el.getBoundingClientRect();
  const dot = document.createElement('div');
  dot.style.cssText = `position:fixed;left:${r.left + r.width / 2 - 28}px;top:${r.top + r.height / 2 - 28}px;
    width:56px;height:56px;border-radius:50%;background:rgba(0,0,0,.28);pointer-events:none;z-index:99999;
    transition:transform .45s ease, opacity .45s ease;transform:scale(.4);opacity:1`;
  document.body.appendChild(dot);
  requestAnimationFrame(() => { dot.style.transform = 'scale(1.3)'; dot.style.opacity = '0'; });
  setTimeout(() => dot.remove(), 600);
}
"""


def record_video(cap, kiosk_url, tv_url, location):
    print("Video")
    VIDEO.mkdir(parents=True, exist_ok=True)
    context = cap.browser.new_context(
        locale="en-GB",
        viewport={"width": 1920, "height": 1080},
        record_video_dir=str(VIDEO / "raw"),
        record_video_size={"width": 1920, "height": 1080},
    )
    stage_url = cap.base + "/__docs_stage"
    html = (
        STAGE_HTML.replace("PHONE_URL", cap.base + location)
        .replace("TV_URL", cap.base + tv_url)
        .replace("KIOSK_URL", cap.base + kiosk_url)
    )
    context.route(stage_url, lambda route: route.fulfill(status=200, content_type="text/html", body=html))

    page = cap.login(context, "marco")
    page.goto(stage_url)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)
    kiosk = page.frame_locator("#kiosk")
    phone = page.frame_locator("#phone")

    def caption(text, hold=0):
        page.evaluate("t => document.getElementById('caption').textContent = t", text)
        page.wait_for_timeout(hold)

    def tap(locator, pause=500):
        locator.scroll_into_view_if_needed()
        locator.evaluate(TAP_JS)
        page.wait_for_timeout(250)
        locator.click()
        page.wait_for_timeout(pause)

    caption("A customer walks in and puts their name in at the door.", 1200)
    name = kiosk.locator("#customer_name")
    tap(name, 200)
    name.press_sequentially("Sam Carter", delay=120)
    page.wait_for_timeout(500)
    tap(kiosk.locator("label.barber-chip:has-text('Marco')"))
    tap(kiosk.locator("button[type=submit]:has-text('Check In')"), 1200)
    caption("They get their place in line. The TV adds them straight away, first name and initial only.", 4200)

    caption("When a chair is free, the barber calls the next person from their phone.", 1500)
    tap(phone.locator("#waiting-list button:has-text('Call to Chair')").first, 2500)
    caption("Everyone waiting sees who's up.", 2500)

    caption("When the cut is done, one tap clears it.", 1200)
    tap(phone.locator("#chair-list button:has-text('Complete')").first, 2800)

    caption("No sign-in sheet, and everyone can see where they are in line.", 3000)
    page.screenshot(path=str(VIDEO / "poster.png"))
    # The home page picture: the three screens alone, without the title or caption.
    page.evaluate("document.querySelector('.title').hidden = true; document.getElementById('caption').textContent = ''")
    page.wait_for_timeout(300)
    page.locator(".devices").screenshot(path=str(VIDEO / "hero.png"))
    page.evaluate("document.querySelector('.title').hidden = false")
    video_path = page.video.path()
    context.close()

    target = VIDEO / "demo.webm"
    Path(video_path).replace(target)
    (VIDEO / "raw").rmdir()
    for name in ("poster", "hero"):
        png = VIDEO / f"{name}.png"
        save(png.read_bytes(), name if name == "hero" else "video-poster", max_width=1920)
        png.unlink()
    print(f"  {target.relative_to(DOCS)}  {target.stat().st_size // 1024} KB")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("phase", choices=["fresh", "demo"])
    parser.add_argument("--base", default="http://127.0.0.1:8090")
    parser.add_argument("--no-video", action="store_true")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        cap = Capture(playwright, args.base)
        if args.phase == "fresh":
            fresh(cap)
        else:
            demo(cap, video=not args.no_video)
        cap.browser.close()


if __name__ == "__main__":
    main()

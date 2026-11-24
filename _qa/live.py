from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(r"C:\Users\ursa\Desktop\agentSpace\particle-christmas-tree\_qa")
URL = "https://minnorursa.github.io/particle-christmas-tree/"
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append("console:" + m.text) if m.type == "error" else None)
    pg.goto(URL, wait_until="load")
    pg.wait_for_timeout(4500)
    pg.screenshot(path=str(OUT / "live.png"))
    info = pg.evaluate("() => ({count: window.__tree.count, q: window.__tree.quality, t: window.__tree.state.t})")
    print("live info:", info)
    print("errors:", errors)
    b.close()
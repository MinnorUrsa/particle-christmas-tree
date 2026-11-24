"""多机位出图：低/中/高俯仰 + 旋转相位，检查自由视角下形体是否成立。"""
import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = ROOT.joinpath("index.html").as_uri()
OUT = ROOT / "_qa"

SHOTS = [
    ("idle", 8.0, 0.10, 0.327),
    ("low", 9.5, -0.26, 0.9),
    ("mid", 11.0, 0.30, 1.9),
    ("high", 12.5, 0.52, 2.7),
    ("back", 14.0, 0.05, 4.0),
]

with sync_playwright() as pw:
    b = pw.chromium.launch()
    p = b.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="no-preference")
    errs = []
    p.on("pageerror", lambda e: errs.append(str(e)))
    p.goto(URL + "?hq=1", wait_until="load")
    p.wait_for_timeout(2600)
    for name, t, pitch, yaw in SHOTS:
        p.evaluate(
            """([t, pitch, yaw]) => {
                const s = window.__tree.state;
                window.__tree.seek(t);
                s.pitch = pitch; s.yaw = yaw; s.vyaw = 0; s.vpitch = 0; s.idle = 0;
                window.__tree.step(1/60, 3);
            }""",
            [t, pitch, yaw],
        )
        p.screenshot(path=str(OUT / f"v3-{name}.png"))
    print("errors:", errs)
    b.close()

"""线上页复验：确认部署的是 v2，并且交互确实生效。"""
import json
import pathlib
import time
import urllib.request

from playwright.sync_api import sync_playwright

URL = "https://minnorursa.github.io/particle-christmas-tree/"
OUT = pathlib.Path(__file__).resolve().parent

for i in range(24):
    try:
        r = urllib.request.urlopen(URL + "?v=2", timeout=30)
        b = r.read().decode("utf-8", "replace")
        ok = "tierProfile" in b and "trailBase" in b and "MERRY CHRISTMAS" in b
        print("http", r.status, len(b), "v2-ok" if ok else "STALE", r.headers.get("last-modified"))
        if ok:
            break
    except Exception as e:
        print("err", e)
    time.sleep(5)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="no-preference")
    errs, cerrs = [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: cerrs.append(m.text) if m.type == "error" else None)
    pg.goto(URL, wait_until="load")
    pg.wait_for_timeout(3000)

    info = pg.evaluate("() => ({count: __tree.count, q: __tree.quality, yaw: __tree.state.yaw})")

    # 拖动旋转 + 惯性
    pg.mouse.move(720, 450)
    pg.mouse.down()
    pg.mouse.move(960, 400, steps=12)
    pg.mouse.up()
    pg.evaluate("() => __tree.step(1/60, 30)")
    orbit = pg.evaluate("() => ({yaw: __tree.state.yaw, pitch: __tree.state.pitch, custom: __tree.cam.custom})")

    # 按住冻结闪烁
    before = pg.evaluate("() => __tree.flash.total")
    pg.evaluate("() => { __tree.touch(720, 450, true); __tree.step(1/60, 60); }")
    held = pg.evaluate("() => ({total: __tree.flash.total, allow: __tree.flash.allow, off: __tree.offsetSum()})")
    pg.evaluate("() => { __tree.release(); __tree.step(1/60, 150); }")
    after = pg.evaluate("() => ({total: __tree.flash.total, allow: __tree.flash.allow, off: __tree.offsetSum()})")

    pg.screenshot(path=str(OUT / "live2.png"))
    print(json.dumps({"info": info, "orbit": orbit,
                      "press": {"before": before, **held},
                      "release": after,
                      "errors": errs[:3], "console": cerrs[:3]}, ensure_ascii=False))
    br.close()

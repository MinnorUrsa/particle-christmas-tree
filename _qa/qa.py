import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright

ROOT = Path(r"C:\Users\ursa\Desktop\agentSpace\particle-christmas-tree")
OUT = Path(r"C:\Users\ursa\Desktop\agentSpace\particle-christmas-tree\_qa")
OUT.mkdir(exist_ok=True)
URL = (ROOT / "index.html").as_uri()

errors = []
logs = []


def diff_score(a: bytes, b: bytes) -> float:
    ia = Image.open(io.BytesIO(a)).convert("RGB")
    ib = Image.open(io.BytesIO(b)).convert("RGB")
    d = ImageChops.difference(ia, ib)
    return sum(ImageStat.Stat(d).mean) / 3.0


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--force-color-profile=srgb", "--enable-gpu-rasterization"])
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.on("console", lambda m: (logs.append(f"{m.type}: {m.text}"),
                                  errors.append(f"console.{m.type}: {m.text}") if m.type in ("error",) else None))
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.goto(URL + "?hq=1", wait_until="load")
    page.wait_for_timeout(3600)

    info = page.evaluate("""() => ({
        count: window.__tree.count,
        fps: window.__tree.fps,
        quality: window.__tree.quality,
        state: {t: window.__tree.state.t, yaw: window.__tree.state.yaw, pitch: window.__tree.state.pitch},
        dpr: window.devicePixelRatio,
        canvas: [document.getElementById('scene').width, document.getElementById('scene').height],
        scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight]
    })""")

    shot1 = page.screenshot()
    (OUT / "desktop-1.png").write_bytes(shot1)
    page.wait_for_timeout(1000)
    shot2 = page.screenshot()
    (OUT / "desktop-2.png").write_bytes(shot2)
    motion = diff_score(shot1, shot2)

    fps = page.evaluate("""() => new Promise(res => {
        let n = 0; const t0 = performance.now();
        function tick(){ n++; const el = performance.now() - t0;
            if (el < 2000) requestAnimationFrame(tick); else res(n / (el / 1000)); }
        requestAnimationFrame(tick);
    })""")

    # seek 到不同相位，验证螺旋与雪的位置确实变化
    seekshots = []
    for t in (6.0, 14.0, 22.0):
        page.evaluate("(t) => window.__tree.seek(t)", t)
        page.wait_for_timeout(160)
        b = page.screenshot()
        seekshots.append(b)
        (OUT / f"seek-{int(t)}.png").write_bytes(b)
    seekdiff = diff_score(seekshots[0], seekshots[1])

    # 点击绽开
    page.mouse.click(720, 480)
    page.wait_for_timeout(380)
    burst_shot = page.screenshot()
    (OUT / "burst.png").write_bytes(burst_shot)
    burst_motion = diff_score(seekshots[2], burst_shot)

    # 手机视口
    mob = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    mob.on("pageerror", lambda e: errors.append(f"mobile pageerror: {e}"))
    mob.goto(URL + "?hq=1", wait_until="load")
    mob.wait_for_timeout(3400)
    mshot = mob.screenshot()
    (OUT / "mobile.png").write_bytes(mshot)
    minfo = mob.evaluate("() => ({count: window.__tree.count, fps: window.__tree.fps, quality: window.__tree.quality})")
    mob.close()

    # 降级路径：不加 hq，跑 12 秒看是否稳定降级且不报错
    deg = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    deg.on("pageerror", lambda e: errors.append(f"degrade pageerror: {e}"))
    deg.goto(URL, wait_until="load")
    deg.wait_for_timeout(12000)
    dinfo = deg.evaluate("() => ({quality: window.__tree.quality, count: window.__tree.count})")
    (OUT / "degraded.png").write_bytes(deg.screenshot())
    deg.close()

    browser.close()

report = {
    "info": info,
    "fps_measured": round(fps, 1),
    "degraded": dinfo,
    "motion_diff": round(motion, 3),
    "seek_diff": round(seekdiff, 3),
    "burst_diff": round(burst_motion, 3),
    "mobile": minfo,
    "errors": errors,
    "console_logs": logs[:20],
}
print(json.dumps(report, ensure_ascii=False, indent=2))

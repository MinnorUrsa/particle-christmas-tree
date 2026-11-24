"""极光冷杉 v2 质检：自由视角 / 拖尾 / 短促闪烁 / 指尖避让与复位。

用 __tree.step() 以固定步长推进模拟，避免无头浏览器低帧率把结论带偏。
"""
import json, math, pathlib, sys
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = ROOT.joinpath("index.html").as_uri()
OUT = ROOT / "_qa"
OUT.mkdir(exist_ok=True)

report = {}
errors = []


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
            reduced_motion="no-preference",
        )
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                if m.type == "error" else None)

        page.goto(URL + "?hq=1", wait_until="load")
        page.wait_for_timeout(3000)

        report["info"] = page.evaluate("""() => ({
            count: window.__tree.count,
            quality: window.__tree.quality,
            yaw: +window.__tree.state.yaw.toFixed(3),
            dist: +window.__tree.state.dist.toFixed(3),
            flashes: window.__tree.flash.total
        })""")

        # ── 1. 空闲自转 ──
        y0 = page.evaluate("() => window.__tree.state.yaw")
        page.evaluate("() => window.__tree.step(1/60, 120)")
        y1 = page.evaluate("() => window.__tree.state.yaw")
        report["idle_spin_2s"] = round(abs(y1 - y0), 4)

        # ── 2. 自由视角：真实鼠标拖拽（水平 + 垂直） ──
        page.evaluate("() => window.__tree.seek(8)")
        st0 = page.evaluate("() => ({yaw: window.__tree.state.yaw, pitch: window.__tree.state.pitch})")
        page.mouse.move(720, 430)
        page.mouse.down()
        for i in range(12):
            page.mouse.move(720 + (i + 1) * 16, 430 + (i + 1) * 4)
            page.wait_for_timeout(16)
        page.screenshot(path=str(OUT / "v2-drag-trail.png"))
        st1 = page.evaluate("() => ({yaw: window.__tree.state.yaw, pitch: window.__tree.state.pitch})")
        page.mouse.up()
        page.evaluate("() => window.__tree.step(1/60, 60)")
        st2 = page.evaluate("() => ({yaw: window.__tree.state.yaw, pitch: window.__tree.state.pitch})")
        report["orbit"] = {
            "yaw_delta": round(abs(st1["yaw"] - st0["yaw"]), 3),
            "pitch_delta": round(abs(st1["pitch"] - st0["pitch"]), 3),
            "coast": round(abs(st2["yaw"] - st1["yaw"]), 3),
            "pitch_clamped": -0.53 <= st2["pitch"] <= 0.87,
        }
        page.screenshot(path=str(OUT / "v2-orbit.png"))

        # ── 3. 滚轮缩放 ──
        d0 = page.evaluate("() => window.__tree.state.distTarget")
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(300)
        d1 = page.evaluate("() => window.__tree.state.distTarget")
        page.evaluate("() => window.__tree.step(1/60, 40)")
        d2 = page.evaluate("() => window.__tree.state.dist")
        report["zoom"] = {"target_before": d0, "target_after": round(d1, 2),
                          "dist_follows": round(d2, 2)}

        # ── 4. 指尖避让 + 按住停闪 + 松手复位 ──
        page.evaluate("() => window.__tree.seek(12)")
        page.evaluate("() => window.__tree.step(1/60, 60)")
        base = page.evaluate("""() => ({
            off: window.__tree.offsetSum(),
            total: window.__tree.flash.total
        })""")

        page.mouse.move(720, 430)
        page.mouse.down()
        for i in range(16):
            page.mouse.move(720 + math.cos(i / 16 * 6.283) * 44,
                            430 + math.sin(i / 16 * 6.283) * 44)
            page.evaluate("() => window.__tree.step(1/60, 2)")
        pressed = page.evaluate("""() => ({
            off: window.__tree.offsetSum(),
            total: window.__tree.flash.total,
            live: window.__tree.flash.live
        })""")
        page.screenshot(path=str(OUT / "v2-touch.png"))

        # 按住 2 秒：闪烁计数必须冻结
        page.evaluate("() => window.__tree.step(1/60, 120)")
        held = page.evaluate("() => ({total: window.__tree.flash.total, off: window.__tree.offsetSum()})")
        report["press"] = {
            "offset_base": round(base["off"], 1),
            "offset_pushed": round(pressed["off"], 1),
            "flash_at_press": pressed["total"],
            "flash_after_2s_hold": held["total"],
            "frozen": pressed["total"] == held["total"],
        }

        # 松手：推进 6 秒，必须回到原位且闪烁恢复
        page.mouse.up()
        page.evaluate("() => window.__tree.step(1/60, 120)")   # 2s
        mid = page.evaluate("() => ({off: window.__tree.offsetSum(), total: window.__tree.flash.total})")
        page.evaluate("() => window.__tree.step(1/60, 240)")   # 再 4s
        end = page.evaluate("""() => ({
            off: window.__tree.offsetSum(),
            total: window.__tree.flash.total,
            live: window.__tree.flash.live
        })""")
        report["release"] = {
            "offset_after_2s": round(mid["off"], 1),
            "offset_after_6s": round(end["off"], 1),
            "flash_at_release": mid["total"],
            "flash_after_6s": end["total"],
            "resumed": end["total"] > mid["total"],
            "ratio_remaining": round(end["off"] / max(pressed["off"], 1), 4),
        }
        page.screenshot(path=str(OUT / "v2-restored.png"))

        # ── 5. 闪烁的"短促"：一个 flash 必须在 0.2s 内衰完 ──
        report["flash"] = page.evaluate("""() => {
            window.__tree.seek(16);
            window.__tree.forceFlash(60);
            window.__tree.step(1/60, 2);
            const a = window.__tree.flash.live;
            window.__tree.step(1/60, 15);
            const b = window.__tree.flash.live;
            return { live_after_2f: a, live_after_17f: b, short: b < a * 0.25 };
        }""")
        # 定格版：抓一张"晃眼"的实拍
        page.evaluate("() => { window.__tree.seek(16); window.__tree.forceFlash(90, 6); window.__tree.step(1/60, 1); }")
        page.screenshot(path=str(OUT / "v2-flash.png"))

        # ── 6. 运动拖尾：高速自转瞬间 ──
        page.evaluate("""() => {
            window.__tree.seek(20);
            window.__tree.state.vyaw = 6.0;
            window.__tree.step(1/60, 30);
        }""")
        page.screenshot(path=str(OUT / "v2-spin-trail.png"))

        # ── 7. 手机档 ──
        mob = browser.new_page(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            reduced_motion="no-preference",
        )
        mob.on("pageerror", lambda e: errors.append(f"mobile pageerror: {e}"))
        mob.goto(URL + "?hq=1", wait_until="load")
        mob.wait_for_timeout(3200)
        mob.screenshot(path=str(OUT / "v2-mobile.png"))
        report["mobile"] = mob.evaluate(
            "() => ({count: window.__tree.count, quality: window.__tree.quality})")
        mob.close()

        # ── 8. 掉帧降级路径 ──
        deg = browser.new_page(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1,
            reduced_motion="no-preference",
        )
        deg.on("pageerror", lambda e: errors.append(f"degrade pageerror: {e}"))
        deg.goto(URL, wait_until="load")
        deg.wait_for_timeout(13000)
        report["degraded"] = deg.evaluate(
            "() => ({quality: window.__tree.quality, fps: +window.__tree.fps.toFixed(1)})")
        deg.close()

        browser.close()


main()

report["errors"] = errors

fail = []
if errors:
    fail.append(f"控制台报错 {len(errors)} 条：{errors[:2]}")
if report["idle_spin_2s"] < 0.02:
    fail.append("空闲自转未生效")
if report["orbit"]["yaw_delta"] < 0.3:
    fail.append("水平拖拽未改变视角")
if report["orbit"]["pitch_delta"] < 0.03:
    fail.append("垂直拖拽未改变俯仰")
if not report["orbit"]["pitch_clamped"]:
    fail.append("俯仰越界")
if report["press"]["offset_pushed"] < report["press"]["offset_base"] + 40:
    fail.append("指尖避让没有推动粒子")
if not report["press"]["frozen"]:
    fail.append("按住时仍在闪烁")
if report["release"]["ratio_remaining"] > 0.02:
    fail.append("松手后粒子未回到原位")
if not report["release"]["resumed"]:
    fail.append("松手后闪烁未恢复")
if not report["flash"]["short"]:
    fail.append("闪烁不够短促")

report["verdict"] = "PASS" if not fail else "FAIL: " + "; ".join(fail)
print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(0 if not fail else 1)

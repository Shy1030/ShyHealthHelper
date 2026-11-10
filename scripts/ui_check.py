"""端到端 UI 冒烟测试：首页、月经、饮食、运动、记账。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = Path(tempfile.gettempdir()) / "mooncare-shots"
SHOTS.mkdir(parents=True, exist_ok=True)
PHOTO = Path(__file__).resolve().parent.parent / "web" / "icons" / "icon-192.png"

errors: list[str] = []


def shot(page, name: str) -> None:
    page.wait_for_timeout(500)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            locale="zh-CN",
        )
        page = context.new_page()
        page.on(
            "console",
            lambda msg: errors.append(f"console.{msg.type}: {msg.text}")
            if msg.type == "error"
            else None,
        )
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        page.wait_for_selector("#heroCard")

        hero = page.locator("#heroCard").inner_text()
        assert "记录你的第一个周期" in hero, f"empty hero mismatch: {hero}"
        print("[ok] home empty state")
        shot(page, "01-home-empty")

        # 月经：记录今天
        page.click('.tab[data-tab="period"]')
        page.wait_for_selector("#calendarGrid .cal-day[data-date]")
        page.click('#periodForm button[type="submit"]')
        page.wait_for_selector("#periodHistory .list-item")
        page.wait_for_function("document.querySelectorAll('#periodHistory .list-item').length >= 1")
        print("[ok] period created")

        # 再补录两个历史周期，让预测有数据
        page.evaluate(
            """async () => {
                const dates = ['2026-09-26', '2026-10-24'];
                for (const d of dates) {
                    await fetch('/api/cycle/periods', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ start_date: d, end_date: null, flow: 'medium' })
                    });
                }
            }"""
        )
        page.reload(wait_until="networkidle")
        page.click('.tab[data-tab="home"]')
        page.wait_for_selector("#homeStats .stat-card")
        hero = page.locator("#heroCard").inner_text()
        assert "周期第" in hero and "Mock" not in hero, f"populated hero mismatch: {hero}"
        print("[ok] prediction rendered on home")
        shot(page, "02-home-populated")

        # 饮食
        page.click('.tab[data-tab="diet"]')
        page.fill("#dietDescription", "一碗米饭、清蒸鲈鱼、清炒西兰花")
        page.click("#dietSubmit")
        page.wait_for_selector("#dietResult .result-card", timeout=20000)
        assert "千卡" in page.locator("#dietResult").inner_text()
        page.wait_for_selector("#dietHistory .list-item")
        print("[ok] diet analysis")

        # 只上传照片、不填写描述
        page.set_input_files("#dietPhoto", str(PHOTO))
        page.click("#dietSubmit")
        page.wait_for_function(
            "document.querySelectorAll('#dietHistory .list-item').length >= 2",
            timeout=20000,
        )
        assert "照片已留档" in page.locator("#dietResult").inner_text()
        print("[ok] photo-only diet analysis")
        shot(page, "03-diet-result")

        # 运动
        page.click('.tab[data-tab="exercise"]')
        page.fill("#profileBirthYear", "1998")
        page.fill("#profileHeight", "165")
        page.fill("#profileWeight", "55")
        page.click("#saveProfile")
        page.wait_for_timeout(600)
        page.click("#generatePlan")
        page.wait_for_selector(".plan-day", timeout=20000)
        days = page.locator(".plan-day").count()
        assert days == 7, f"expected 7 plan days, got {days}"
        print("[ok] exercise plan")
        shot(page, "04-exercise-plan")

        # 记账
        page.click('.tab[data-tab="finance"]')
        page.wait_for_selector("#financeCategory option", state="attached")
        page.fill("#financeAmount", "25.5")
        page.fill("#financeNote", "午饭")
        page.click('#financeForm button[type="submit"]')
        page.wait_for_selector("#financeList .list-item")
        page.wait_for_function(
            "document.querySelector('#sumExpense').textContent.includes('25.50')"
        )
        print("[ok] finance record")
        shot(page, "05-finance")

        page.click('.tab[data-tab="home"]')
        page.wait_for_selector("#homeStats .stat-card")
        shot(page, "06-home-final")

        browser.close()

    if errors:
        print("CONSOLE/PAGE ERRORS:")
        for error in errors:
            print(" -", error)
        return 1

    print("ALL UI CHECKS PASSED")
    print("screenshots:", SHOTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())

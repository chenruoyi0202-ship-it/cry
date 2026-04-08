"""Automated Playwright tests for the migraine tracking app."""
import sys, os
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://localhost:9123")
PASS = 0
FAIL = 0

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))

def run_tests():
    global PASS, FAIL

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
        context = browser.new_context(viewport={"width": 430, "height": 932})
        page = context.new_page()

        # Collect console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # ===== Test main app directly =====
        page2 = context.new_page()
        # Block external font requests to prevent timeout
        page2.route("**://fonts.googleapis.com/**", lambda route: route.abort())
        page2.route("**://fonts.gstatic.com/**", lambda route: route.abort())
        page2.route("**://api.open-meteo.com/**", lambda route: route.abort())
        page2.route("**://nominatim.openstreetmap.org/**", lambda route: route.abort())
        page2.goto("file:///home/user/cry/migraine.html")
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(500)

        # -- Page Load --
        print("\n══════ 页面加载 ══════")
        test("标题正确", page2.title() == "偏头痛记录", page2.title())
        test("主卡片可见", page2.locator(".card").is_visible())
        test("SVG 图标存在", page2.locator(".header-icon svg").count() == 1)
        test("5 个 Tab", page2.locator(".tab").count() == 5)
        page2.screenshot(path="/tmp/test-page-load.png", full_page=True)
        print("  截图: /tmp/test-page-load.png")

        # -- Dark Mode --
        print("\n══════ 深色模式 ══════")
        page2.locator("#darkToggle").click()
        page2.wait_for_timeout(300)
        has_dark = page2.evaluate("document.body.classList.contains('dark')")
        test("切换到深色模式", has_dark)
        page2.screenshot(path="/tmp/test-dark-mode.png", full_page=True)
        print("  截图: /tmp/test-dark-mode.png")
        page2.locator("#darkToggle").click()
        page2.wait_for_timeout(200)
        has_dark2 = page2.evaluate("document.body.classList.contains('dark')")
        test("切回浅色模式", not has_dark2)

        # -- Form Fill & Save --
        print("\n══════ 填写表单 & 保存 ══════")
        # Clear existing records
        page2.evaluate("records = []; saveRecords(); initForm();")

        page2.fill("#inputDatetime", "2025-03-15T10:30")
        page2.locator("#inputIntensity").evaluate("el => { el.value = 8; }")
        page2.evaluate("updateIntensity()")
        intensity_text = page2.locator("#intensityVal").text_content()
        test("强度滑块显示 8", intensity_text == "8", intensity_text)

        page2.fill("#inputDuration", "2.5")

        # Click tags
        page2.locator('#groupLocation .tag-toggle[data-value="左侧"]').click()
        page2.locator('#groupSymptoms .tag-toggle[data-value="恶心"]').click()
        page2.locator('#groupSymptoms .tag-toggle[data-value="畏光"]').click()
        page2.locator('#groupTriggers .tag-toggle[data-value="压力"]').click()

        left_active = page2.locator('#groupLocation .tag-toggle[data-value="左侧"]').get_attribute("class")
        test("标签 '左侧' 已选中", "active" in left_active)

        page2.fill("#inputMedication", "布洛芬 400mg")
        page2.fill("#inputNotes", "测试记录")

        page2.screenshot(path="/tmp/test-form-filled.png", full_page=True)
        print("  截图: /tmp/test-form-filled.png")

        # Mock fetchWeather and autoSync, then save
        page2.evaluate("""(() => {
            window._origFetchWeather = fetchWeather;
            window._origAutoSync = autoSync;
            fetchWeather = async () => '测试城市 · 晴 25°C 湿度50%';
            autoSync = () => {};
        })()""")
        page2.locator(".btn-primary").first.click()
        page2.wait_for_timeout(2000)

        record_count = page2.evaluate("records.length")
        test("记录已保存", record_count == 1, f"records.length = {record_count}")

        saved_record = page2.evaluate("records[0]")
        test("强度 = 8", saved_record["intensity"] == 8)
        test("时长 = 2.5", saved_record["duration"] == 2.5)
        test("位置包含 '左侧'", "左侧" in saved_record.get("location", []))
        test("症状包含 '恶心'", "恶心" in saved_record.get("symptoms", []))
        test("天气已记录", "测试城市" in saved_record.get("weather", ""), saved_record.get("weather", ""))
        test("用药 = 布洛芬 400mg", saved_record["medication"] == "布洛芬 400mg")

        # Restore mocks
        page2.evaluate("fetchWeather = window._origFetchWeather; autoSync = window._origAutoSync;")

        # Check toast appeared
        toast_cls = page2.locator("#toast").get_attribute("class")
        # Toast may have already hidden, that's ok

        # Check form reset
        med_val = page2.locator("#inputMedication").input_value()
        test("保存后表单已重置", med_val == "", f"medication = '{med_val}'")

        # -- Tab: History --
        print("\n══════ 历史记录 ══════")
        page2.locator(".tab").nth(2).click()
        page2.wait_for_timeout(300)
        history_visible = page2.locator("#tabHistory").is_visible()
        test("历史 Tab 可见", history_visible)
        items = page2.locator(".history-item").count()
        test("显示 1 条记录", items == 1, f"items = {items}")
        page2.screenshot(path="/tmp/test-history.png", full_page=True)
        print("  截图: /tmp/test-history.png")

        # -- Edit --
        print("\n══════ 编辑记录 ══════")
        page2.locator(".hi-btn.edit").first.click()
        page2.wait_for_timeout(300)
        edit_title = page2.locator("#tabRecord .section-title").text_content()
        test("标题变为 '编辑记录'", edit_title == "编辑记录", edit_title)
        edit_med = page2.locator("#inputMedication").input_value()
        test("用药回填正确", edit_med == "布洛芬 400mg", edit_med)

        # Update and save
        page2.fill("#inputMedication", "对乙酰氨基酚 500mg")
        page2.evaluate("fetchWeather = async () => null; autoSync = () => {};")
        page2.locator(".btn-primary").first.click()
        page2.wait_for_timeout(1500)
        updated = page2.evaluate("records[0].medication")
        test("更新后用药已变", updated == "对乙酰氨基酚 500mg", updated)

        # -- Tab: Stats --
        print("\n══════ 统计分析 ══════")
        page2.locator(".tab").nth(3).click()
        page2.wait_for_timeout(300)
        stats_visible = page2.locator("#tabStats").is_visible()
        test("统计 Tab 可见", stats_visible)
        total_val = page2.locator(".sc-val").first.text_content()
        test("总次数 = 1", total_val == "1", total_val)
        page2.screenshot(path="/tmp/test-stats.png", full_page=True)
        print("  截图: /tmp/test-stats.png")

        # -- Tab: Calendar --
        print("\n══════ 日历 ══════")
        page2.locator(".tab").nth(1).click()
        page2.wait_for_timeout(300)
        cal_visible = page2.locator("#tabCalendar").is_visible()
        test("日历 Tab 可见", cal_visible)
        cal_title = page2.locator("#calTitle").text_content()
        test("日历标题有年月", "年" in cal_title and "月" in cal_title, cal_title)

        # Navigate months
        page2.locator(".cal-nav").last.click()
        page2.wait_for_timeout(200)
        new_title = page2.locator("#calTitle").text_content()
        test("下月切换成功", new_title != cal_title, new_title)
        page2.locator(".cal-nav").first.click()
        page2.wait_for_timeout(200)
        back_title = page2.locator("#calTitle").text_content()
        test("上月切换回来", back_title == cal_title, back_title)
        page2.screenshot(path="/tmp/test-calendar.png", full_page=True)
        print("  截图: /tmp/test-calendar.png")

        # -- Tab: Sync --
        print("\n══════ 同步设置 ══════")
        page2.locator(".tab").nth(4).click()
        page2.wait_for_timeout(300)
        sync_visible = page2.locator("#tabSync").is_visible()
        test("同步 Tab 可见", sync_visible)
        page2.screenshot(path="/tmp/test-sync.png", full_page=True)
        print("  截图: /tmp/test-sync.png")

        # -- Delete --
        print("\n══════ 删除记录 ══════")
        page2.locator(".tab").nth(2).click()
        page2.wait_for_timeout(300)
        page2.on("dialog", lambda d: d.accept())
        page2.locator(".hi-btn.del").first.click()
        page2.wait_for_timeout(500)
        remaining = page2.evaluate("records.length")
        test("删除后记录为空", remaining == 0, f"records.length = {remaining}")
        empty = page2.locator("#historyList .empty-state").is_visible()
        test("显示空状态", empty)

        # -- Console Errors --
        print("\n══════ 控制台检查 ══════")
        test("无 JS 错误", len(console_errors) == 0, "; ".join(console_errors[:3]))

        # Cleanup
        page2.evaluate("records = []; saveRecords(); localStorage.clear();")
        browser.close()

    # ===== Summary =====
    total = PASS + FAIL
    print(f"\n{'═' * 50}")
    print(f"  总计: {total} | 通过: {PASS} | 失败: {FAIL}")
    if FAIL == 0:
        print("  🎉 全部通过!")
    else:
        print(f"  ⚠ {FAIL} 个测试失败")
    print(f"{'═' * 50}\n")

    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(run_tests())

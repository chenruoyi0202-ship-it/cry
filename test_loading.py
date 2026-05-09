"""Test: unlock works with fresh context (no cache) and with cache"""
from playwright.sync_api import sync_playwright
import sys

URL = "http://localhost:9100/love.html"
PASSWORD = "cryxyx"
P, F = 0, 0

def test(name, ok, detail=""):
    global P, F
    if ok: P += 1; print(f"  ✅ {name}")
    else: F += 1; print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # === Test 1: Fresh load (no cache, simulates new device) ===
    print("\n🔒 Test 1: Fresh device (no cache)")
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    page.goto(URL)
    page.wait_for_timeout(1000)

    test("Lock screen shows", page.locator("#lockScreen").is_visible())

    # No loading overlay blocking
    loading_visible = page.locator("#appLoading").is_visible()
    test("No loading overlay blocking", not loading_visible)

    # Enter password
    page.locator("#pwdInput").fill(PASSWORD)
    page.locator("#unlockBtn").click()

    # Button should show progress text
    page.wait_for_timeout(500)
    btn_text = page.locator("#unlockBtn").inner_text()
    print(f"  ℹ️  Button: '{btn_text}'")

    # Wait for app (up to 30s — Pages fetch for 2MB may be slow)
    try:
        page.locator("#app.show").wait_for(timeout=30000)
        test("App loaded", True)
    except:
        page.screenshot(path="/tmp/fix_load_fail.png")
        # Check if error message shown
        err_text = page.locator("#lockError").inner_text()
        test("App loaded", False, f"error: '{err_text}', screenshot saved")
        ctx.close()
        browser.close()
        sys.exit(1)

    # Verify data loaded
    test("Has anniversaries", page.locator(".ann-card").count() > 0)

    page.locator(".tab-btn").nth(1).click()
    page.wait_for_timeout(300)
    test("Has diary entries", page.locator(".tl-card").count() > 0)

    page.locator(".tab-btn").nth(2).click()
    page.wait_for_timeout(1000)
    test("Has gallery photos", page.locator(".gallery-item").count() > 0)

    page.screenshot(path="/tmp/fix_load_ok.png")
    ctx.close()

    # === Test 2: Cached load (simulates refresh) ===
    print("\n🔄 Test 2: Refresh (with cache)")
    ctx2 = browser.new_context(viewport={"width": 390, "height": 844})
    page2 = ctx2.new_page()

    # Pre-seed cache by visiting first
    page2.goto(URL)
    page2.wait_for_timeout(1000)
    page2.locator("#pwdInput").fill(PASSWORD)
    page2.locator("#unlockBtn").click()
    try:
        page2.locator("#app.show").wait_for(timeout=30000)
    except:
        pass

    # Now refresh (simulates cache hit)
    page2.reload()
    try:
        page2.locator("#app.show").wait_for(timeout=10000)
    except:
        pass
    app_visible = page2.locator("#app").is_visible()
    test("Auto-unlock from cache", app_visible)

    if app_visible:
        test("Data preserved", page2.locator(".ann-card").count() > 0)

    ctx2.close()
    browser.close()

print(f"\n{'='*40}")
print(f"📊 Results: {P} passed, {F} failed")
if F > 0: sys.exit(1)

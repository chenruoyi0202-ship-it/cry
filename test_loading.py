"""Test loading works without cache (simulates new device)"""
from playwright.sync_api import sync_playwright
import os, sys

URL = "http://localhost:8770/love.html"
PASSWORD = "cryxyx"
PASS = 0
FAIL = 0

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

with sync_playwright() as p:
    # Fresh context = no cache, no cookies (simulates new device)
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()

    print("\n🔒 Test 1: Fresh load (no cache)")
    page.goto(URL)
    page.wait_for_timeout(1500)

    # Lock screen should show
    test("Lock screen visible", page.locator("#lockScreen").is_visible())
    page.screenshot(path="/tmp/load_01_lock.png")

    # Unlock
    page.locator("#pwdInput").fill(PASSWORD)
    page.locator("#unlockBtn").click()

    # Wait for loading overlay (should show progress)
    page.wait_for_timeout(500)
    loading = page.locator("#appLoading")
    if loading.is_visible():
        load_text = page.locator("#loadText").inner_text()
        print(f"  ℹ️  Loading: {load_text}")
        page.screenshot(path="/tmp/load_02_loading.png")

    # Wait for app to appear (max 30s for slow Pages)
    try:
        page.locator("#app.show").wait_for(timeout=30000)
        test("App loaded within 30s", True)
    except:
        page.screenshot(path="/tmp/load_03_timeout.png")
        test("App loaded within 30s", False, "still loading, screenshot saved")
        browser.close()
        sys.exit(1)

    page.screenshot(path="/tmp/load_04_loaded.png")

    # Check data loaded
    ann_cards = page.locator(".ann-card").count()
    test("Anniversary data loaded", ann_cards > 0, f"got {ann_cards}")

    # Switch to diary
    page.locator(".tab-btn").nth(1).click()
    page.wait_for_timeout(300)
    diary_cards = page.locator(".tl-card").count()
    test("Diary data loaded", diary_cards > 0, f"got {diary_cards}")

    # Check diary detail scrolls
    if diary_cards > 0:
        page.locator(".tl-entry").first.click()
        page.wait_for_timeout(500)
        overlay = page.locator("#diaryDetailOverlay")
        test("Diary detail opens", "open" in (overlay.get_attribute("class") or ""))

        # Check it's scrollable
        overflow = overlay.evaluate("el => getComputedStyle(el).overflowY")
        test("Diary detail scrollable", overflow == "auto", f"overflow-y: {overflow}")
        page.screenshot(path="/tmp/load_05_diary_detail.png")

        page.locator(".dd-close").click()
        page.wait_for_timeout(300)

    # Switch to gallery
    page.locator(".tab-btn").nth(2).click()
    page.wait_for_timeout(2000)  # Wait for lazy photo loading
    photos = page.locator(".gallery-item").count()
    test("Gallery photos visible", photos > 0, f"got {photos}")
    page.screenshot(path="/tmp/load_06_gallery.png")

    # Test lightbox
    if photos > 0:
        page.locator(".gallery-item").first.click()
        page.wait_for_timeout(500)
        lb = page.locator("#lightbox")
        test("Lightbox opens", "open" in (lb.get_attribute("class") or ""))

        # Check blurred background
        bg_img = page.locator("#lbBg").evaluate("el => el.style.backgroundImage")
        test("Lightbox has blurred bg", bg_img and bg_img != "none", bg_img[:50] if bg_img else "none")
        page.screenshot(path="/tmp/load_07_lightbox.png")

        page.locator(".lb-close").click()
        page.wait_for_timeout(300)

    print(f"\n{'='*40}")
    print(f"📊 Results: {PASS} passed, {FAIL} failed")
    print(f"📸 Screenshots: /tmp/load_*.png")

    browser.close()
    if FAIL > 0:
        sys.exit(1)

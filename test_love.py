"""
Automated tests for love.html - couple's memorial webpage
Tests: lock screen, unlock, tab navigation, UI elements, lightbox, diary detail
"""
from playwright.sync_api import sync_playwright
import os, sys

PASS = 0
FAIL = 0
RESULTS = []

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(f"  ✅ {name}")
    else:
        FAIL += 1
        RESULTS.append(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

def flush():
    global RESULTS
    for r in RESULTS: print(r)
    RESULTS.clear()

URL = "http://localhost:8766/love.html"
PASSWORD = "cryxyx"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})

    # ===== 1. Lock Screen =====
    print("\n🔒 Lock Screen Tests")
    page.goto(URL)
    page.wait_for_timeout(1500)

    lock = page.locator("#lockScreen")
    test("Lock screen visible", lock.is_visible())
    page.screenshot(path="/tmp/love_01_lock.png")

    pwd_input = page.locator("#pwdInput")
    test("Password input exists", pwd_input.count() > 0)

    unlock_btn = page.locator("#unlockBtn")
    test("Unlock button exists", unlock_btn.count() > 0)

    # Unlock with correct password
    pwd_input.fill(PASSWORD)
    unlock_btn.click()
    page.wait_for_timeout(3000)

    app = page.locator("#app")
    app_visible = app.is_visible()
    test("Correct password unlocks app", app_visible)
    page.screenshot(path="/tmp/love_02_unlocked.png")

    flush()

    if not app_visible:
        print("\n⛔ Unlock failed. Check /tmp/love_02_unlocked.png")
        browser.close()
        sys.exit(1)

    # ===== 2. Tab Navigation =====
    print("\n📑 Tab Navigation Tests")
    tabs = page.locator(".tab-btn")
    test("4 tabs exist", tabs.count() == 4, f"got {tabs.count()}")

    tab_names = [tabs.nth(i).inner_text() for i in range(tabs.count())]
    test("Tab names correct", tab_names == ["纪念日", "点滴", "相册", "足迹"], str(tab_names))
    test("First tab active", "active" in (tabs.nth(0).get_attribute("class") or ""))

    for i in range(4):
        tabs.nth(i).click()
        page.wait_for_timeout(400)
        test(f"Tab '{tab_names[i]}' activates", "active" in (tabs.nth(i).get_attribute("class") or ""))

    flush()

    # ===== 3. Anniversaries Tab =====
    print("\n🎉 Anniversaries Tab Tests")
    tabs.nth(0).click()
    page.wait_for_timeout(300)

    test("Anniversary timeline exists", page.locator("#annTimeline").count() > 0)
    test("Anniversary grid exists", page.locator("#annScroll").count() > 0)

    ann_cards = page.locator(".ann-card")
    test("Anniversary cards rendered", ann_cards.count() > 0, f"got {ann_cards.count()}")

    tl_nodes = page.locator(".ann-tl-node")
    test("Timeline nodes rendered", tl_nodes.count() > 0, f"got {tl_nodes.count()}")
    page.screenshot(path="/tmp/love_03_anniversaries.png")

    flush()

    # ===== 4. Diary Tab =====
    print("\n📝 Diary Tab Tests")
    tabs.nth(1).click()
    page.wait_for_timeout(300)

    test("Diary timeline exists", page.locator("#timeline").count() > 0)

    diary_cards = page.locator(".tl-card")
    diary_count = diary_cards.count()
    test("Diary cards rendered", diary_count > 0, f"got {diary_count}")
    page.screenshot(path="/tmp/love_04_diary.png")

    # Click diary card to open detail
    if diary_count > 0:
        page.locator(".tl-entry").first.click()
        page.wait_for_timeout(600)
        overlay = page.locator("#diaryDetailOverlay")
        is_open = "open" in (overlay.get_attribute("class") or "")
        test("Diary detail opens on click", is_open)

        if is_open:
            test("Blurred background exists", page.locator("#ddBg").count() > 0)
            page.screenshot(path="/tmp/love_05_diary_detail.png")

            page.locator(".dd-close").click()
            page.wait_for_timeout(400)
            test("Diary detail closes", "open" not in (overlay.get_attribute("class") or ""))

    flush()

    # ===== 5. Gallery Tab =====
    print("\n📷 Gallery Tab Tests")
    tabs.nth(2).click()
    page.wait_for_timeout(500)

    test("Gallery container exists", page.locator("#gallery").count() > 0)

    gallery_items = page.locator(".gallery-item")
    photo_count = gallery_items.count()
    test("Gallery photos rendered", photo_count > 0, f"got {photo_count}")

    if photo_count > 0:
        cols = page.locator("#gallery").evaluate("el => getComputedStyle(el).columnCount")
        test("Waterfall layout (3 columns)", cols == "3", f"got {cols}")

    test("Tag bar exists", page.locator("#categoryBar").count() > 0)
    test("Tag chips rendered", page.locator(".cat-chip").count() > 0, f"got {page.locator('.cat-chip').count()}")
    page.screenshot(path="/tmp/love_06_gallery.png")

    # Lightbox
    if photo_count > 0:
        gallery_items.first.click()
        page.wait_for_timeout(500)
        lb = page.locator("#lightbox")
        lb_open = "open" in (lb.get_attribute("class") or "")
        test("Lightbox opens", lb_open)

        if lb_open:
            test("Lightbox blurred bg", page.locator("#lbBg").count() > 0)
            test("Lightbox image loaded", (page.locator("#lbImg").get_attribute("src") or "") != "")
            test("Lightbox counter", (page.locator("#lbCounter").inner_text() or "") != "")
            page.screenshot(path="/tmp/love_07_lightbox.png")

            page.locator(".lb-close").click()
            page.wait_for_timeout(300)
            test("Lightbox closes", "open" not in (lb.get_attribute("class") or ""))

    flush()

    # ===== 6. Travel Map Tab =====
    print("\n🗺️ Travel Map Tab Tests")
    tabs.nth(3).click()
    page.wait_for_timeout(500)

    test("Map container exists", page.locator("#travelMap").count() > 0)
    test("Places list exists", page.locator("#placesList").count() > 0)
    page.screenshot(path="/tmp/love_08_map.png")

    flush()

    # ===== 7. Edit Mode =====
    print("\n✏️ Edit Mode Tests")
    edit_btn = page.locator("#editToggle")
    test("Edit FAB exists", edit_btn.is_visible())

    edit_btn.click(force=True)
    page.wait_for_timeout(300)
    body_cls = page.locator("body").get_attribute("class") or ""
    test("Edit mode activates", "editing" in body_cls)

    test("Save bar visible", "show" in (page.locator("#saveBar").get_attribute("class") or ""))

    add_btns = page.locator(".add-btn")
    visible_count = sum(1 for i in range(add_btns.count()) if add_btns.nth(i).is_visible())
    test("Add buttons visible", visible_count > 0, f"got {visible_count}")

    edit_btn.click(force=True)
    page.wait_for_timeout(300)
    test("Edit mode deactivates", "editing" not in (page.locator("body").get_attribute("class") or ""))
    page.screenshot(path="/tmp/love_09_edit.png")

    flush()

    # ===== 8. Theme & Sync =====
    print("\n⚙️ Misc Tests")
    test("Sync FAB exists", page.locator("#syncToggle").is_visible())
    test("Theme toggle exists", page.locator("#themeToggle").count() > 0)

    # Toggle dark mode
    page.locator("#themeToggle").click()
    page.wait_for_timeout(300)
    theme = page.locator("html").get_attribute("data-theme")
    test("Dark mode toggles", theme == "dark")
    page.screenshot(path="/tmp/love_10_dark.png")

    flush()

    browser.close()

# Summary
print(f"\n{'='*40}")
print(f"📊 Results: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
print(f"📸 Screenshots saved to /tmp/love_*.png")
if FAIL == 0:
    print("🎉 All tests passed!")
else:
    print(f"⚠️  {FAIL} test(s) need attention")

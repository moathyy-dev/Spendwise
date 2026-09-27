"""One-off Playwright smoke test for the running Streamlit app on :8765.
Not part of the shipped test suite — used only during development QA."""
import time

from playwright.sync_api import sync_playwright

URL = "http://localhost:8765"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", headless=True)
        page = browser.new_page()
        page.goto(URL, timeout=30000)
        page.wait_for_timeout(2000)

        print("STEP1: intro screen")
        btn = page.get_by_text("فهمت، ابدأ الاستخدام")
        if btn.count() > 0:
            btn.first.click()
            page.wait_for_timeout(2000)

        print("STEP2: create family member")
        name_input = page.get_by_label("اسم العضو (مثال: أنا، الوالد، الوالدة)")
        if name_input.count() > 0:
            name_input.fill("معاذ")
            page.get_by_test_id("stBaseButton-secondary").first.click()
            page.wait_for_timeout(2000)

        print("STEP3: navigate to dashboard")
        home_radio = page.get_by_text("🏠 لوحة المعلومات")
        if home_radio.count() > 0:
            home_radio.first.click()
            page.wait_for_timeout(2000)
        print(page.title())

        print("STEP4: navigate to import wizard")
        import_radio = page.get_by_text("📥 استيراد بيانات جديدة")
        if import_radio.count() > 0:
            import_radio.first.click()
            page.wait_for_timeout(2000)

        print("STEP5: navigate to rules")
        rules_radio = page.get_by_text("🏷️ التصنيفات والقواعد")
        if rules_radio.count() > 0:
            rules_radio.first.click()
            page.wait_for_timeout(2000)

        print("STEP6: navigate to budget")
        budget_radio = page.get_by_text("🎯 الميزانية الشهرية")
        if budget_radio.count() > 0:
            budget_radio.first.click()
            page.wait_for_timeout(2000)

        print("STEP7: navigate to reports")
        reports_radio = page.get_by_text("📊 التقارير والنسخ الاحتياطي")
        if reports_radio.count() > 0:
            reports_radio.first.click()
            page.wait_for_timeout(2000)

        print("STEP8: navigate to settings")
        settings_radio = page.get_by_text("⚙️ الإعدادات")
        if settings_radio.count() > 0:
            settings_radio.first.click()
            page.wait_for_timeout(2000)

        # Check for Streamlit exception boxes anywhere along the way
        errors = page.locator("text=Traceback").count()
        print("TRACEBACK_COUNT:", errors)

        browser.close()


if __name__ == "__main__":
    main()

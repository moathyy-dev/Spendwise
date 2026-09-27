"""Playwright smoke test for the full import -> review -> commit -> dashboard
round trip, using the synthetic Arabic sample Excel file. Development QA
only, not part of the shipped test suite."""
import os

from playwright.sync_api import sync_playwright

URL = "http://localhost:8767"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_FILE = os.path.join(PROJECT_ROOT, "sample_data", "statements", "نموذج_كشف_حساب_عربي.xlsx")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", headless=True)
        page = browser.new_page()
        page.goto(URL, timeout=30000)
        page.wait_for_timeout(2000)

        intro_btn = page.get_by_text("فهمت، ابدأ الاستخدام")
        if intro_btn.count() > 0:
            intro_btn.first.click()
            page.wait_for_timeout(1500)

        name_input = page.get_by_label("اسم العضو (مثال: أنا، الوالد، الوالدة)")
        if name_input.count() > 0:
            name_input.fill("معاذ")
            page.get_by_test_id("stBaseButton-secondary").first.click()
            page.wait_for_timeout(2000)

        print("Navigating to import wizard...")
        page.get_by_text("📥 استيراد بيانات جديدة").first.click()
        page.wait_for_timeout(2000)

        new_account_label = page.get_by_label("اسم/رمز الحساب الجديد (مثال: الحساب الجاري، بطاقة الراجحي)")
        if new_account_label.count() > 0:
            new_account_label.fill("الحساب الجاري")

        print("Uploading sample file...")
        file_input = page.locator("input[type='file']").first
        file_input.set_input_files(SAMPLE_FILE)
        page.wait_for_timeout(3000)

        page.get_by_text("متابعة", exact=True).first.click()
        page.wait_for_timeout(4000)

        errors = page.locator("text=Traceback").count()
        print("TRACEBACK_COUNT after upload:", errors)
        print(page.content()[:200])

        print("Confirming column mapping...")
        continue_btn = page.get_by_text("متابعة إلى المعالجة والمراجعة")
        if continue_btn.count() > 0:
            continue_btn.first.click()
            page.wait_for_timeout(6000)

        errors2 = page.locator("text=Traceback").count()
        print("TRACEBACK_COUNT after categorize:", errors2)

        print("Committing import...")
        commit_btn = page.get_by_text("✅ تأكيد وحفظ")
        if commit_btn.count() > 0:
            commit_btn.first.click()
            page.wait_for_timeout(4000)

        errors3 = page.locator("text=Traceback").count()
        print("TRACEBACK_COUNT after commit:", errors3)

        success = page.get_by_text("تم حفظ المعاملات المعتمدة بنجاح")
        print("SUCCESS_MESSAGE_FOUND:", success.count() > 0)

        page.screenshot(path="/tmp/qa_after_commit.png", full_page=True)

        print("Navigating to dashboard...")
        page.get_by_text("🏠 لوحة المعلومات").first.click()
        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/qa_dashboard.png", full_page=True)

        errors4 = page.locator("text=Traceback").count()
        print("TRACEBACK_COUNT on dashboard:", errors4)

        browser.close()


if __name__ == "__main__":
    main()

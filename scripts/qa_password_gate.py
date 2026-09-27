"""Playwright smoke test verifying the password gate blocks/unblocks access
correctly. Development QA only."""
from playwright.sync_api import sync_playwright

URL = "http://localhost:8768"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", headless=True)
        page = browser.new_page()
        page.goto(URL, timeout=30000)
        page.wait_for_timeout(2000)

        locked_title = page.get_by_text("🔒 SpendWise")
        print("PASSWORD_GATE_SHOWN:", locked_title.count() > 0)
        page.screenshot(path="/tmp/qa_password_gate_locked.png", full_page=True)

        pwd_input = page.get_by_label("كلمة المرور")
        pwd_input.fill("wrong-password")
        page.get_by_text("دخول").first.click()
        page.wait_for_timeout(1500)
        wrong_msg = page.get_by_text("كلمة المرور غير صحيحة")
        print("WRONG_PASSWORD_REJECTED:", wrong_msg.count() > 0)

        pwd_input2 = page.get_by_label("كلمة المرور")
        pwd_input2.fill("test-secret-123")
        page.get_by_text("دخول").first.click()
        page.wait_for_timeout(2000)

        still_locked = page.get_by_text("🔒 SpendWise")
        print("STILL_LOCKED_AFTER_CORRECT_PASSWORD:", still_locked.count() > 0)
        page.screenshot(path="/tmp/qa_password_gate_unlocked.png", full_page=True)

        browser.close()


if __name__ == "__main__":
    main()

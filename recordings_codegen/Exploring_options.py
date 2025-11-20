import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://linear.app/testing-multi-agent-ui/team/TES/active")
    page.get_by_role("button", name="Continue with email").click()
    page.get_by_role("textbox", name="Enter your email address…").fill("kdhulipalla13@gmail.com")
    page.get_by_role("button", name="Continue with email").click()
    page.get_by_role("button", name="Enter code manually").click()
    page.get_by_role("textbox", name="Enter code").fill("B38R7S6RUH")
    page.get_by_role("link", name="Issues", exact=True).click()
    page.get_by_role("main").get_by_role("button", name="Create new issue").click()
    page.get_by_role("button", name="Create issue").click()
    page.get_by_role("dialog", name="Create issue").click()
    page.locator("#team-testing_multi_agent_ui").get_by_role("link", name="Projects").click()
    page.get_by_role("button", name="Create new project").click()
    page.get_by_role("button", name="Create project").click()
    page.get_by_role("button", name="Discard project").click()
    page.locator("#team-testing_multi_agent_ui").get_by_role("link", name="Views").click()
    page.get_by_role("button", name="Create view").click()
    page.get_by_role("button", name="Views", exact=True).get_by_role("link").click()
    page.get_by_role("button", name="Create view").click()
    page.get_by_role("button", name="Projects", exact=True).get_by_role("link").click()
    page.locator("div").filter(has_text=re.compile(r"^More$")).nth(3).click()
    page.locator("div").filter(has_text=re.compile(r"^Teams$")).nth(2).click()
    page.locator("div").filter(has_text=re.compile(r"^More$")).nth(3).click()
    page.get_by_label("Members").get_by_text("Members").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)

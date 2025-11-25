import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://linear.app/testing-multi-agent-ui/team/TES/active")
    page.get_by_role(
        "button", name="Testing_multi_agent_UI Workspace Menu").click()
    page.get_by_role("option", name="Settings").click()
    page.get_by_role("link", name="Profile").click()
    page.get_by_role("textbox", name="Full name").click()
    page.get_by_role("textbox", name="Full name").press("ArrowRight")
    page.get_by_role("textbox", name="Full name").press("ArrowRight")
    page.get_by_role("textbox", name="Full name").press("ArrowRight")
    page.get_by_role("textbox", name="Full name").press("ArrowRight")
    page.get_by_role("textbox", name="Full name").press("ArrowRight")
    page.get_by_role("textbox", name="Full name").press("ArrowRight")
    page.get_by_role("textbox", name="Full name").press("ArrowRight")
    page.get_by_role("textbox", name="Full name").fill("Krishna a")
    page.get_by_role("textbox", name="Full name").press("Shift+Home")
    page.get_by_role("textbox", name="Full name").fill(
        "kdhulipalla13@gmail.com")
    page.locator("div").filter(has_text="ProfileProfile").nth(4).click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)

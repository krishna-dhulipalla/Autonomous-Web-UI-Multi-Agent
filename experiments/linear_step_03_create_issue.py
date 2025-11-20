import json, re
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

OUTPUT_DIR = Path("artifacts/linear_demo/step_03_create_issue")

TEAM_URL = "https://linear.app/testing-multi-agent-ui/team/TES/active"  # replace with your team


# ---------------------------------------------------------------------
# Helper: ALWAYS take screenshot with a step name (even on errors)
# ---------------------------------------------------------------------
def snap(page, name: str):
    path = OUTPUT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"📸 Screenshot: {path}")
    return str(path)


# ---------------------------------------------------------------------
# Helper: Safe action wrapper — never crash Playwright mid modal
# ---------------------------------------------------------------------
def safe_click(page, locator, step_name):
    try:
        locator.click(timeout=5000)
    except Exception as e:
        print(f"⚠️ Click failed at {step_name}: {e}")
        snap(page, f"error_{step_name}")
        raise


def safe_fill(page, locator, text, step_name):
    try:
        locator.fill(text, timeout=5000)
    except Exception as e:
        print(f"⚠️ Fill failed at {step_name}: {e}")
        snap(page, f"error_{step_name}")
        raise


# ---------------------------------------------------------------------
# MAIN create-issue function (based on your codegen)
# ---------------------------------------------------------------------
def create_issue(page):
    print("➡️ Opening New Issue modal…")
    modal_btn = page.get_by_role("main").get_by_role("button", name="Create new issue")
    safe_click(page, modal_btn, "open_new_issue_modal")

    snap(page, "step_03_01_modal_opened")

    # Title
    print("➡️ Filling Title…")
    title_box = page.get_by_role("textbox", name="Issue title").locator("p")
    safe_click(page, title_box, "title_open")
    title_box.fill("My test issue from Playwright")
    snap(page, "step_03_02_title_filled")

    # Description
    print("➡️ Filling Description…")
    desc_box = page.get_by_role("textbox", name="Issue description").locator("p")
    safe_click(page, desc_box, "description_open")
    desc_box.fill("This issue was created automatically by playwright.")
    snap(page, "step_03_03_description_filled")

    # Status
    print("➡️ Changing Status…")
    safe_click(page, page.get_by_role("combobox", name="Change status"), "open_status")
    safe_click(page, page.get_by_role("option", name="Backlog"), "set_status_backlog")

    safe_click(page, page.get_by_role("combobox", name="Change status"), "reopen_status")
    safe_click(page, page.get_by_text("In Progress"), "set_status_progress")
    snap(page, "step_03_04_status_set")

    # Priority
    print("➡️ Changing Priority…")
    safe_click(page, page.get_by_role("combobox", name="Change priority. No priority"), "open_priority")
    priority_opt = page.locator("div").filter(has_text=re.compile(r"^High$"))
    safe_click(page, priority_opt, "priority_high_set")
    snap(page, "step_03_05_priority_set")

    # Assignee
    print("➡️ Changing Assignee…")
    safe_click(page, page.get_by_role("combobox", name="Change assignee. Currently no"), 
               "open_assignee")
    safe_click(page, page.get_by_role("option", name="kdhulipalla13@gmail.com"),
               "assignee_set")
    snap(page, "step_03_06_assignee_set")

    # # Labels
    # print("➡️ Setting Labels…")
    # safe_click(page, page.get_by_role("combobox", name="Change labels"), "open_labels")
    # safe_click(page, page.locator('[id="1feature"] > .sc-gmHgPJ > .sc-iaHxGD'), 
    #            "label_feature_set")

    # # Close label dropdown
    # page.locator(".sc-dzKBZk").click()
    # snap(page, "step_03_07_labels_set")

    # Due date
    print("➡️ Setting Due Date…")
    safe_click(page, page.get_by_role("combobox", name="More actions"), 
               "open_more_actions")
    safe_click(page, page.get_by_text("Set due date⇧D▶"), 
               "open_due_date")
    safe_click(page, page.get_by_text("Tomorrow"),
               "due_tomorrow")
    snap(page, "step_03_08_due_date_set")

    # Final modal state
    snap(page, "step_03_09_before_create")

    # Create issue
    print("🟢 Creating Issue…")
    final_create = page.get_by_role("button", name="Create issue")
    safe_click(page, final_create, "issue_create")

    snap(page, "step_03_10_after_created")

    return True


# ---------------------------------------------------------------------
# MAIN RUN
# ---------------------------------------------------------------------
def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:

        # ⭐ Persistent browser with stored profile
        context = p.chromium.launch_persistent_context(
            "playwright_profile",   # folder to store cookies/session
            headless=False,
            slow_mo=150
        )

        # You do NOT create the browser this way anymore:
        # browser = p.chromium.launch()

        page = context.new_page()

        # --- Login only once ---
        page.goto("https://linear.app/")
        print("👉 If this is your first run, log in manually.")
        print("👉 On future runs, Linear should already be logged in.")
        input("Press Enter to continue… ")

        # Navigate to your team
        page.goto(TEAM_URL)
        page.wait_for_timeout(2000)
        snap(page, "step_03_00_team_loaded")

        # Actual automation logic
        create_issue(page)

        print("\n🎉 Issue created!")
        print("⭐ Browser will stay open. Close it manually when you're done.")
        input("Press Enter to end the script (browser stays open)…")


if __name__ == "__main__":
    run()
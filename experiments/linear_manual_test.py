from pathlib import Path
from playwright.sync_api import sync_playwright
import json

TEAM_URL = "https://linear.app/testing-multi-agent-ui/team/TES/active"
OUTPUT_DIR = Path("artifacts/linear_demo")

def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        page = browser.new_page()

        # 1) Go to Linear home / login
        page.goto("https://linear.app/")
        print("✅ Opened https://linear.app/")

        # 2) Let you log in manually (only for this early phase)
        print(
            "\n👉 Please log in to Linear in the browser window."
            "\n   Open your workspace if needed."
            "\n   When you see you are logged in, come back here and press Enter."
        )
        input("\nPress Enter when you're logged in... ")

        # 3) Now automate: go directly to team/board URL
        print(f"\n🚀 Navigating to team board: {TEAM_URL}")
        page.goto(TEAM_URL)

        # Give the page a moment to fully render UI
        page.wait_for_timeout(3000)

        # 4) Take screenshot
        screenshot_path = OUTPUT_DIR / "step_01_team_board.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"📸 Screenshot saved to: {screenshot_path}")

        # 5) Save simple metadata for this step
        step_metadata = {
            "step_name": "open_team_board",
            "description": "Open Linear team board and capture UI state.",
            "url": page.url,
            "screenshot": str(screenshot_path),
        }

        metadata_path = OUTPUT_DIR / "step_01_team_board.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(step_metadata, f, indent=2)

        print(f"📝 Metadata saved to: {metadata_path}")

        # 6) Keep browser open so you can visually confirm
        input("\n✅ Done! Press Enter to close the browser...")
        browser.close()


if __name__ == "__main__":
    run()
from pathlib import Path
from playwright.sync_api import sync_playwright


URL = "https://linear.app/testing-multi-agent-ui/team/TES/active"         
OUT = Path("artifacts/dom_dump")
OUT.mkdir(parents=True, exist_ok=True)


def run():
    with sync_playwright() as p:
        # Use persistent context so login works too
        context = p.chromium.launch_persistent_context(
            "playwright_profile",
            headless=False,
            slow_mo=100
        )
        page = context.new_page()

        print(f"Navigating to: {URL}")
        page.goto(URL)
        page.wait_for_timeout(2000)

        # ---------------------------
        # 1) Extract full DOM (HTML)
        # ---------------------------
        html = page.content()
        dom_path = OUT / "dom.html"
        dom_path.write_text(html, encoding="utf-8")
        print(f"📄 Full DOM saved to: {dom_path}")

        # ---------------------------
        # 2) Extract visible interactable elements
        # ---------------------------
        visible_elems = []

        # Buttons
        for b in page.get_by_role("button").all():
            try:
                text = b.inner_text().strip()
            except:
                text = ""
            visible_elems.append({"type": "button", "text": text})

        # Links
        for l in page.get_by_role("link").all():
            try:
                text = l.inner_text().strip()
            except:
                text = ""
            visible_elems.append({"type": "link", "text": text})

        # Inputs / textboxes
        for t in page.get_by_role("textbox").all():
            try:
                text = t.inner_text().strip()
            except:
                text = ""
            visible_elems.append({"type": "textbox", "text": text})

        # Save visible element summary
        import json
        elems_path = OUT / "visible_elements.json"
        elems_path.write_text(json.dumps(visible_elems, indent=2), encoding="utf-8")
        print(f"🔍 Visible elements saved to: {elems_path}")

        # ---------------------------
        # 3) Screenshot of UI state
        # ---------------------------
        screenshot_path = OUT / "screenshot.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"📸 Screenshot saved to: {screenshot_path}")

        print("\nDone. Open the files inside artifacts/dom_dump/ to inspect.")


if __name__ == "__main__":
    run()

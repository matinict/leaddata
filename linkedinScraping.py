import json
import os
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# ==================== CONFIGURATION ====================
# The profile you want to scrape
TARGET_URL = "https://www.linkedin.com/in/matinr/"
BASE_OUTPUT_DIR = "output"
# Path to your existing credentials file
CREDS_PATH = "input/social_credentials.json"

def get_profile_handle(url):
    """Extracts the unique handle (e.g., 'matinr') from the LinkedIn URL."""
    return url.strip("/").split("/")[-1]

def load_linkedin_session():
    """Extracts the li_at cookie from your social_credentials.json."""
    try:
        if not os.path.exists(CREDS_PATH):
            print(f"❌ Error: {CREDS_PATH} not found.")
            return None

        with open(CREDS_PATH, "r") as f:
            creds = json.load(f)
            # Pulls from the LinkedIn block in your structured JSON
            token = creds.get("LinkedIn", {}).get("access_token")
            return token
    except Exception as e:
        print(f"❌ Error loading credentials: {e}")
        return None

def scrape_linkedin():
    # Setup output directory based on handle
    profile_handle = get_profile_handle(TARGET_URL)
    profile_dir = os.path.join(BASE_OUTPUT_DIR, profile_handle)
    os.makedirs(profile_dir, exist_ok=True)

    session_token = load_linkedin_session()

    with sync_playwright() as p:
        # 1. Launch Browser
        browser = p.chromium.launch(headless=True)

        # Use a realistic User Agent to bypass standard bot detection
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        # 2. Inject the li_at session cookie
        if session_token:
            context.add_cookies([{
                "name": "li_at",
                "value": session_token,
                "domain": ".www.linkedin.com",
                "path": "/",
                "secure": True,
                "sameSite": "None"
            }])
            print("🍪 Session cookie injected successfully.")
        else:
            print("⚠️ No session token found. Script will likely hit an auth-wall.")

        page = context.new_page()
        stealth = Stealth()
        stealth.apply_stealth_sync(page)

        # 3. Navigation with Timeout Fix
        print(f"🚀 Navigating to: {TARGET_URL}")
        try:
            # Using 'domcontentloaded' avoids the 30s timeout from background trackers
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"⚠️ Navigation warning: {e}")

        # --- AUTHENTICATION CHECK ---
        # If the URL contains 'authwall' or 'login', the injected cookie is invalid
        if "authwall" in page.url or "login" in page.url:
            print("❌ AUTH FAILURE: LinkedIn redirected to login. Update your li_at token.")
            page.screenshot(path=os.path.join(profile_dir, "auth_error.png"))
            browser.close()
            return

        # 4. Content Loading & Wait
        try:
            print("⏳ Waiting for profile content to render...")
            page.wait_for_selector("h1.text-heading-xlarge", timeout=15000)
            print("✅ Profile authenticated and content detected.")
        except Exception:
            print("⚠️ Timeout: Profile content not found. Check debug screenshot.")
            page.screenshot(path=os.path.join(profile_dir, "timeout_debug.png"))

        # Scroll to trigger lazy-loaded sections (About, Experience)
        page.evaluate("window.scrollTo(0, 600);")
        page.wait_for_timeout(2000)

        # 5. Data Extraction
        profile_data = {
            "timestamp": datetime.now().isoformat(),
            "handle": profile_handle,
            "url": TARGET_URL,
            "name": page.locator("h1.text-heading-xlarge").first.inner_text().strip() if page.locator("h1.text-heading-xlarge").count() > 0 else "N/A",
            "headline": page.locator(".text-body-medium").first.inner_text().strip() if page.locator(".text-body-medium").count() > 0 else "N/A",
            "about": page.locator("section#about-section + div, #about ~ div").first.inner_text().strip() if page.locator("section#about-section").count() > 0 or page.locator("#about ~ div").count() > 0 else "N/A"
        }

        # 6. Save JSON Output
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = os.path.join(profile_dir, f"profile_data_{timestamp_str}.json")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Success! Data saved to: {file_path}")
        browser.close()

if __name__ == "__main__":
    scrape_linkedin()

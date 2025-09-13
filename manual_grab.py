import asyncio
import requests
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# ==============================
# Playwright helpers
# ==============================

async def fetch_tokens_with_playwright(box_url):
    """
    Launch Playwright to fetch CSRF/request tokens and cookies from Box
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(box_url)
        await page.wait_for_load_state("networkidle")

        # Grab page HTML
        html = await page.content()

        csrf_token = None
        request_token = None

        # Look for requestToken in Box bootstrap config
        match = re.search(r'"requestToken":"([^"]+)"', html)
        if match:
            request_token = match.group(1)

        # Look for CSRFToken in JS variables
        match = re.search(r'CSRFToken["\']?\s*[:=]\s*["\']([^"\']+)', html)
        if match:
            csrf_token = match.group(1)

        # Pull cookies
        cookies = await context.cookies()

        await browser.close()
        return csrf_token, request_token, cookies

def integrate_cookies(session, cookies):
    """
    Copy cookies from Playwright into requests.Session
    """
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))

# ==============================
# Main download logic
# ==============================

def get_box_download_link(box_url):
    """
    Extract download link from Box share URL by making POST request to Box API.
    Will try Playwright first, then fall back to regex/requests.
    """
    parsed = urlparse(box_url)
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) < 4 or path_parts[0] != 'v':
        raise ValueError("Invalid Box URL format")

    vanity_name = path_parts[1]
    file_id = path_parts[3]

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0',
    })

    csrf_token, request_token, cookies = None, None, []

    # --- Step 1: Try Playwright ---
    try:
        csrf_token, request_token, cookies = asyncio.run(fetch_tokens_with_playwright(box_url))
        integrate_cookies(session, cookies)
        print(f"[Playwright] CSRF: {csrf_token}, Request: {request_token}")
    except Exception as e:
        print(f"[Playwright] Failed: {e}")

    # --- Step 2: Fallback: requests scraping ---
    if not csrf_token and not request_token:
        print("[Requests fallback] Fetching page...")
        page_response = session.get(box_url)
        if page_response.ok:
            # Extract requestToken
            match = re.search(r'"requestToken":"([^"]+)"', page_response.text)
            if match:
                request_token = match.group(1)

            # Extract CSRFToken
            match = re.search(r'CSRFToken["\']?\s*[:=]\s*["\']([^"\']+)', page_response.text)
            if match:
                csrf_token = match.group(1)
        print(f"[Requests fallback] CSRF: {csrf_token}, Request: {request_token}")

    # --- Build POST request ---
    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    api_url = f"{base_domain}/index.php?rm=box_download_shared_file&vanity_name={vanity_name}&file_id=f_{file_id}"

    post_data = {
        'rm': 'box_download_shared_file',
        'vanity_name': vanity_name,
        'file_id': f'f_{file_id}'
    }
    if csrf_token:
        post_data['csrf_token'] = csrf_token
    if request_token:
        post_data['request_token'] = request_token

    print(f"[POST] {api_url}")
    print(f"[POST data] {post_data}")

    resp = session.post(api_url, data=post_data, allow_redirects=False)
    print(f"[POST response] {resp.status_code}")
    if resp.status_code in [302, 303]:
        return resp.headers.get('Location')
    return None

def download_file_from_box(box_url, save_path=None):
    """
    Complete function to get download link and download file
    """
    download_url = get_box_download_link(box_url)
    if not download_url:
        print("Could not get download URL")
        return None

    print(f"Downloading from: {download_url[:100]}...")
    resp = requests.get(download_url, stream=True)
    if resp.status_code != 200:
        print(f"Download failed: {resp.status_code}")
        return None

    if not save_path:
        cd = resp.headers.get('Content-Disposition', '')
        match = re.search(r'filename[*]?=["\']?([^"\';\r\n]*)', cd)
        if match:
            save_path = match.group(1)
        else:
            save_path = f"file_{box_url.split('/')[-1]}"

    with open(save_path, 'wb') as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    print(f"File saved as: {save_path}")
    return save_path

# ==============================
# Example usage
# ==============================

if __name__ == "__main__":
    box_url = "https://nrcs.app.box.com/v/naip/file/1057693042742"
    try:
        download_file_from_box(box_url, "downloaded_file.zip")
    except Exception as e:
        print(f"Download failed: {e}")

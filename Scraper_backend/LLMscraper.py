from dotenv import load_dotenv

load_dotenv()

import time
import json
import threading
import hashlib
import re
import os
import requests
from datetime import datetime, date
from typing import Optional

from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
import redis

from Scraper_backend.datasetManager import json_to_excel
from Scraper_backend.semantic import semantic_filter

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

start_time = time.perf_counter()

BASE_DIR = os.path.dirname(__file__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
print(f"[Config] Gemini key: {'SET (' + GEMINI_API_KEY[:8] + '...)' if GEMINI_API_KEY else 'MISSING'}")

CURRENCY_TO_INR = {
    "GBP": 107,
    "USD": 83,
    "EUR": 90,
    "AUD": 54,
    "CAD": 61,
    "SGD": 62,
    "INR": 1,
}

r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

print("Flushing previous tender data from Redis...")
for key in r.scan_iter("tender:*"):
    r.delete(key)
print("Redis flushed.")

# ---------------------------------------------------------------------------
# Keywords / sectors
# ---------------------------------------------------------------------------

keywordIndexes = ["Health", "Defence", "Corporate", "Pets"]
keywordList = []

for fname in ["Health.json", "Defence.json", "Corporate.json", "Pets.json"]:
    with open(os.path.join(BASE_DIR, fname), "r") as fh:
        keywordList.append(json.load(fh))

# ---------------------------------------------------------------------------
# Adapter config
# ---------------------------------------------------------------------------

adapters = [
    {
        "url": "https://www.find-tender.service.gov.uk/Search/Results",
        "iframe": ["False"],
        "refreshMode": "dom",
        "keywordSearchBox": "input#keywords",
        "submitButton": "button#adv_search_button",
        "IdentifierForTenderList": [[1, "div.notice-search-results"], "div.search-result"],
        "NextPageButton": "a.standard-paginate-next",
        "InitialTenderLinks": "a.search-result-rwh",
        "ResultsIndicatorText": "We've found 0 notices",
        "Country": "UK",
        "BackButton": [False],
    }
]


# SECTION 1 — LLM EXTRACTION


EXTRACTION_PROMPT = """You are a specialist in UK government procurement notices.
You will receive the raw HTML (or rendered text) of a single tender notice page.
Extract the fields below and return ONLY a valid JSON object — no markdown fences,
no explanation, nothing else.

Required fields (use null if not found):
{{
  "Tender Title": "string",
  "Tender Description": "string",
  "Organisation Name": "string",
  "Original Currency": "ISO 4217 code, e.g. GBP",
  "Budget Min": number or null,
  "Budget Max": number or null,
  "Opening Date": "DD Month YYYY or 'not available'",
  "Closing Date": "DD Month YYYY or 'not available'",
  "Tender Status": "Open | Closed | Awarded | Unknown",
  "Award Date": "DD Month YYYY or 'not available'",
  "Country": "string"
}}

Rules:
1. Opening Date
- First look for an explicit tender opening/publication date.
- If an "Opening Date" field is not present, use the date shown next to or after "Published".
  Examples:
    - Published 16 June 2026
    - Published: 16 June 2026
- The "Published" date should be treated as the Opening Date.
- If neither exists, return "not available".

2. Closing Date
- Extract the tender submission deadline.
- Common labels include:
  - Closing date
  - Closing time
  - Deadline
  - Submission deadline
  - Response deadline
  - Date offers to be received
- Return only the date in "DD Month YYYY" format.
- If no closing date exists, return "not available".

3. For Budget Min / Budget Max: if only one value is given, set both to that value.
  If a range is given (e.g. lowest lot to highest lot), use those as min and max.
4. For Tender Status: derive from whether a submission deadline exists and whether
  it has passed relative to today ({today}).
5. Strip any boilerplate cookie banners, navigation menus, and footer text —
  focus only on the notice content.
5. Return ONLY the JSON object.

Page content:
{page_content}
"""


def extract_fields_with_gemini(page_html: str) -> dict:
    """
    Send the page content to Gemini and get structured tender fields back.
    Returns a dict with the extracted fields, or an empty dict on failure.
    """
    today_str = date.today().strftime("%d %B %Y")
    prompt = EXTRACTION_PROMPT.format(
        today=today_str,
        page_content=page_html[:40000],
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "temperature": 0,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        raw_text = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "text" in part:
                    raw_text += part["text"]

        print(f"[Gemini RAW RESPONSE]:\n{repr(raw_text[:500])}")

        # Remove thinking tags if present
        raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

        # Extract the first { ... } JSON block
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if not match:
            print(f"[Gemini] No JSON object found in response: {raw_text[:300]}")
            return {}

        try:
            return json.loads(match.group())
        except json.JSONDecodeError as e:
            print(f"[Gemini] JSON parse failed: {e}\nRaw: {match.group()[:300]}")
            return {}

    except Exception as exc:
        print(f"[Gemini extraction error] {exc}")
        return {}


# SECTION 2 — POST-PROCESSING

def resolve_currency_and_budget(extracted: dict) -> tuple:
    currency = (extracted.get("Original Currency") or "").upper().strip() or None
    budget_min = extracted.get("Budget Min")
    budget_max = extracted.get("Budget Max")
    inr_min = None
    inr_max = None
    if currency and currency in CURRENCY_TO_INR:
        rate = CURRENCY_TO_INR[currency]
        if budget_min is not None:
            inr_min = int(budget_min * rate)
        if budget_max is not None:
            inr_max = int(budget_max * rate)
    return currency, budget_min, budget_max, inr_min, inr_max


def resolve_sector(keyword: str) -> str:
    for idx, category in enumerate(keywordList):
        if keyword in category.get("words", []):
            return keywordIndexes[idx]
    return "Unknown"


def resolve_keywords(title: str, description: str) -> list:
    combined = f"{title or ''} {description or ''}".lower()
    matched = []
    for category in keywordList:
        for word in category.get("words", []):
            if word.lower() in combined and word not in matched:
                matched.append(word)
    return matched


def compute_timeline(opening_date_str: Optional[str], closing_date_str: Optional[str]) -> Optional[int]:
    if not opening_date_str or not closing_date_str:
        return None
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            o = datetime.strptime(opening_date_str.strip(), fmt)
            c = datetime.strptime(closing_date_str.strip(), fmt)
            return (c - o).days
        except ValueError:
            continue
    return None


def build_tender_object(extracted: dict, tender_url: str, search_keyword: str, country: str) -> dict:
    currency, budget_min, budget_max, inr_min, inr_max = resolve_currency_and_budget(extracted)
    sector = resolve_sector(search_keyword)
    title = extracted.get("Tender Title") or ""
    description = extracted.get("Tender Description") or ""
    matched_keywords = resolve_keywords(title, description)
    opening_date = extracted.get("Opening Date")
    closing_date = extracted.get("Closing Date")
    timeline = compute_timeline(opening_date, closing_date)
    primary_key = hashlib.md5(
        (title + (extracted.get("Organisation Name") or "")).encode()
    ).hexdigest()

    return {
        "Primary Key": primary_key,
        "Tender Title": title or None,
        "Tender Description": description or None,
        "Organisation Name": extracted.get("Organisation Name"),
        "Tender Status": extracted.get("Tender Status"),
        "Award Date": extracted.get("Award Date"),
        "Country": extracted.get("Country") or country,
        "Sector": sector,
        "Budget Currency": currency,
        "Budget in Local Currency Minimum": budget_min,
        "Budget in Local Currency Maximum": budget_max,
        "Budget in INR Minimum": inr_min,
        "Budget in INR Maximum": inr_max,
        "Opening Date": opening_date,
        "Expiry Date": closing_date,
        "Timeline": timeline,
        "Link to the Tender": tender_url,
        "Keywords": matched_keywords,
        "Keyword included": search_keyword,
        "Order Quantity": None,
        "Special Observation": None,
        "Eligibility": None,
        "Application Status": "Not Applied",
        "Current Applicants": None,
    }


def store_tender(tender_object: dict) -> None:
    primary_key = tender_object["Primary Key"]
    redis_key = f"tender:{primary_key}"
    cached = r.get(redis_key)
    if cached:
        cached_obj = json.loads(cached)
        existing_keywords = set(cached_obj.get("Keywords", []))
        new_keywords = set(tender_object.get("Keywords", []))
        tender_object["Keywords"] = list(existing_keywords | new_keywords)
        r.set(redis_key, json.dumps(tender_object))
        print(f"Updated existing tender -> {primary_key}")
    else:
        r.set(redis_key, json.dumps(tender_object))
        print(json.dumps(tender_object, indent=4))
        print("---------------------------------------")


# ===========================================================================
# SECTION 3 — PLAYWRIGHT NAVIGATION
# ===========================================================================

def get_iframe_query_string(returnContentDocument, adapter):
    selectorStr = "document"
    if adapter["iframe"][0] == "True":
        if isinstance(adapter["iframe"][1], list):
            for level in adapter["iframe"][1]:
                if isinstance(level, list):
                    selectorStr += f"?.querySelectorAll('{level[1]}')[{int(level[0]) - 1}]"
                else:
                    selectorStr += f"?.querySelector('{level}')"
            return f"{selectorStr}?.contentDocument" if returnContentDocument else selectorStr
        else:
            selectorStr += f"?.querySelector('{adapter['iframe']}')"
            return f"{selectorStr}?.contentDocument" if returnContentDocument else selectorStr
    return selectorStr


def getElementQueryString(elementKey, adapter):
    selectorStr = get_iframe_query_string(True, adapter) if adapter["iframe"][0] == "True" else "document"
    if elementKey == "BackButton":
        if isinstance(adapter[elementKey][1], list):
            for level in adapter[elementKey][1]:
                if isinstance(level, list):
                    selectorStr += f"?.querySelectorAll('{level[1]}')[{int(level[0]) - 1}]"
                else:
                    selectorStr += f"?.querySelector('{level}')"
            return selectorStr
        else:
            selectorStr += f"?.querySelector('{adapter[elementKey]}')"
            return selectorStr
    config = adapter.get(elementKey)
    if isinstance(config, list):
        for level in config:
            if isinstance(level, list):
                selectorStr += f"?.querySelectorAll('{level[1]}')[{int(level[0]) - 1}]"
            else:
                selectorStr += f"?.querySelector('{level}')"
    elif isinstance(config, str):
        selectorStr += f"?.querySelector('{config}')"
    return selectorStr


def getElementQueryStringForListItems(adapter):
    selectorStr = get_iframe_query_string(True, adapter) if adapter["iframe"][0] == "True" else "document"
    if isinstance(adapter["IdentifierForTenderList"], list):
        for level in adapter["IdentifierForTenderList"]:
            if isinstance(level, list):
                selectorStr += f"?.querySelectorAll('{level[1]}')[{int(level[0]) - 1}]"
            else:
                selectorStr += f"?.querySelectorAll('{level}')"
    else:
        selectorStr += f"?.querySelectorAll('{adapter['IdentifierForTenderList']}')"
    return selectorStr


def get_leaf_selector(selector_value):
    if isinstance(selector_value, str):
        return f"?.querySelector('{selector_value}')"
    if isinstance(selector_value, list):
        selectorStr = ""
        for level in selector_value:
            if isinstance(level, list):
                if not isinstance(level[0], int):
                    selectorStr += f"?.querySelectorAll('{level[1]}')"
                    selectorStr += f"[listItem{selectorStr}{level[0]}]"
                else:
                    selectorStr += f"?.querySelectorAll('{level[1]}')[{int(level[0]) - 1}]"
            else:
                selectorStr += f"?.querySelectorAll('{level}')"
        return selectorStr
    return str(selector_value)


def install_custom_selector_loop(page, adapter):
    script = f"""
        () => {{
            window.__assignTenderCustomSelectors = () => {{
                let iterator = 0;
                let parent = document;

                if ("{adapter["iframe"][0]}" == "True") {{
                    parent = {get_iframe_query_string(True, adapter)};
                    if (!parent) return;
                }}

                const tenderCards = {getElementQueryStringForListItems(adapter)};

                tenderCards?.forEach((listItem) => {{
                    listItem.classList.add(`custom-tenderList-${{iterator}}`);

                    const InitialTenderLink = listItem{get_leaf_selector(adapter["InitialTenderLinks"])};
                    if (InitialTenderLink) {{
                        InitialTenderLink.classList.add(`custom-InitialTenderLinks-${{iterator}}-0`);
                    }}

                    iterator += 1;
                }});

                const NextPageButton = {getElementQueryString("NextPageButton", adapter)};
                if (NextPageButton) NextPageButton.classList.add("custom-NextPageButton");

                const keywordSearchElement = {getElementQueryString("keywordSearchBox", adapter)};
                if (keywordSearchElement) keywordSearchElement.classList.add("custom-keywordSearchElement");

                const submitButtonElement = {getElementQueryString("submitButton", adapter)};
                if (submitButtonElement) submitButtonElement.classList.add("custom-submitButtonElement");
            }};

            window.__assignTenderCustomSelectors();

            if (window.__customSelectorInterval) clearInterval(window.__customSelectorInterval);
            window.__customSelectorInterval = setInterval(() => {{ window.__assignTenderCustomSelectors(); }}, 250);
        }}
    """
    page.evaluate(script)


def wait_for_js_visible(page, js_selector, timeout=60000, poll_interval=0.25):
    start = time.time()
    while True:
        try:
            is_visible = page.evaluate(f"""
                () => {{
                    const element = {js_selector};
                    if (!element) return false;
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return (
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        style.opacity !== "0" &&
                        rect.width > 0 &&
                        rect.height > 0
                    );
                }}
            """)
        except Exception as e:
            if "Execution context was destroyed" in str(e) or "navigation" in str(e).lower():
                if (time.time() - start) * 1000 > timeout:
                    raise PlaywrightTimeoutError(f"Timeout: {js_selector}")
                time.sleep(poll_interval)
                continue
            raise
        if is_visible:
            return True
        if (time.time() - start) * 1000 > timeout:
            raise PlaywrightTimeoutError(f"Timeout: {js_selector}")
        time.sleep(poll_interval)


def wait_for_url_change(page, old_url, timeout=30000):
    page.wait_for_function("oldUrl => window.location.href !== oldUrl", arg=old_url, timeout=timeout)


def get_results_signature(page, adapter):
    try:
        return page.evaluate(f"""
            () => {{
                let doc = document;
                if ("{adapter["iframe"][0]}" == "True") {{
                    doc = {get_iframe_query_string(True, adapter)};
                    if (!doc || !doc.body) return "NO_DOC";
                }}
                const bodyText = doc.body?.innerText || "";
                const noResultsPresent = bodyText.includes({json.dumps(adapter["ResultsIndicatorText"])});
                const firstCard = {getElementQueryStringForListItems(adapter)};
                const firstCardText = firstCard ? firstCard.innerText.trim() : "";
                return JSON.stringify({{
                    url: window.location.href,
                    noResultsPresent,
                    firstCardText,
                    bodyLength: bodyText.length
                }});
            }}
        """)
    except Exception as e:
        return f"ERROR:{str(e)}"


def wait_for_results_signature_change_or_stability(page, adapter, before_signature, timeout=60000, poll_interval=0.5, stable_for=1.5):
    start = time.time()
    last_signature = None
    stable_since = None
    while True:
        current_signature = get_results_signature(page, adapter)
        if current_signature != before_signature:
            if current_signature == last_signature:
                if stable_since and time.time() - stable_since >= stable_for:
                    return current_signature
            else:
                last_signature = current_signature
                stable_since = time.time()
        if (time.time() - start) * 1000 > timeout:
            return current_signature
        time.sleep(poll_interval)


def wait_for_tender_results_refresh(page, adapter, old_first_card_text=None):
    try:
        return page.evaluate(f"""
            (args) => {{
                let doc = document;
                if ("{adapter["iframe"][0]}" == "True") {{
                    doc = {get_iframe_query_string(True, adapter)};
                    if (!doc || !doc.body) return [false, false, "iframe not ready"];
                }}
                const bodyText = doc.body?.innerText || "";
                if (bodyText.includes(args.noResultsText)) return [true, true, "no results"];
                const firstCard = {getElementQueryStringForListItems(adapter)};
                if (!firstCard) return [false, false, "no first card"];
                return [true, false, "results loaded"];
            }}
        """, {"oldText": old_first_card_text, "noResultsText": adapter["ResultsIndicatorText"]})
    except Exception as e:
        return [False, False, str(e)]


def click_and_wait_for_refresh(page, submit_button, adapter, timeout=60000):
    refresh_mode = adapter.get("refreshMode", "dom")
    if refresh_mode == "navigation":
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout):
                submit_button.click()
        except Exception:
            submit_button.click()
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
    else:
        before_signature = get_results_signature(page, adapter)
        submit_button.click()
        wait_for_results_signature_change_or_stability(page, adapter, before_signature=before_signature, timeout=timeout)


# ===========================================================================
# SECTION 4 — MAIN SCRAPE LOOP
# ===========================================================================

def process_tender_page(page, adapter, search_keyword, country):
    tender_url = page.url
    try:
        page_content = page.evaluate("() => document.body.innerText")
    except Exception:
        page_content = ""

    if not page_content.strip():
        print(f"Empty page content for {tender_url}, skipping.")
        return

    extracted = extract_fields_with_gemini(page_content)

    if not extracted:
        print(f"Gemini returned no data for {tender_url}, skipping.")
        return

    tender_obj = build_tender_object(
        extracted=extracted,
        tender_url=tender_url,
        search_keyword=search_keyword,
        country=country,
    )
    store_tender(tender_obj)


def runMainLogic(page, parent, keyword, category, adapter, timer=1):
    install_custom_selector_loop(page, adapter)

    try:
        lists = parent.locator('[class*="custom-tenderList-"]')
        lists.first.wait_for(state="attached", timeout=60000)
    except Exception:
        return

    tender_count = lists.count()

    for listNumber in range(tender_count):
        install_custom_selector_loop(page, adapter)
        card = lists.nth(listNumber)

        # No status filtering — Gemini extracts status from each page
        # Just visit every card and let the LLM decide

        element = card.locator('[class*="custom-InitialTenderLinks-"]').first
        old_url = page.evaluate("() => window.location.href")
        before_signature = get_results_signature(page, adapter)

        try:
            element.click()
            wait_for_url_change(page, old_url)
            wait_for_results_signature_change_or_stability(page, adapter, before_signature=before_signature)
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception as e:
            print(f"Navigation error: {e}. Skipping.")
            continue

        try:
            process_tender_page(page, adapter, search_keyword=keyword, country=adapter["Country"])
        except Exception as e:
            print(f"Error processing tender page: {e}")

        # Go back to results
        before_signature = get_results_signature(page, adapter)
        if adapter["BackButton"][0]:
            try:
                back_btn = page.evaluate_handle(
                    f"() => {getElementQueryString('BackButton', adapter)}"
                ).as_element()
                if back_btn:
                    back_btn.click()
            except Exception:
                page.go_back(wait_until="domcontentloaded", timeout=60000)
        else:
            page.go_back(wait_until="domcontentloaded", timeout=60000)

        wait_for_results_signature_change_or_stability(page, adapter, before_signature=before_signature)

        for state in ("domcontentloaded", "networkidle"):
            try:
                page.wait_for_load_state(state, timeout=10000)
            except Exception:
                pass

        wait_for_js_visible(page, getElementQueryString("keywordSearchBox", adapter))
        install_custom_selector_loop(page, adapter)

    # Pagination
    before_signature = get_results_signature(page, adapter)
    try:
        nextPageButton = parent.locator(".custom-NextPageButton")
        nextPageButton.first.wait_for(state="attached")
        if nextPageButton.is_disabled():
            return
        old_first_text = parent.locator('[class*="custom-tenderList-"]').first.inner_text(timeout=3000)
        nextPageButton.click()
        wait_for_results_signature_change_or_stability(page, adapter, before_signature=before_signature)
        wait_for_tender_results_refresh(page=page, old_first_card_text=old_first_text, adapter=adapter)
        runMainLogic(page, parent, keyword, category, adapter, timer=2)
    except Exception:
        return


def scrape_site(adapter):
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(adapter["url"], timeout=1200000)
        parent = page

        for category in keywordList:
            for keyword in category["words"]:
                for state in ("domcontentloaded", "networkidle"):
                    try:
                        page.wait_for_load_state(state, timeout=10000)
                    except Exception:
                        pass

                install_custom_selector_loop(page, adapter)

                try:
                    search_box = parent.locator(".custom-keywordSearchElement")
                    search_box.first.wait_for(state="visible", timeout=60000)
                    search_box.fill(keyword)
                except PlaywrightTimeoutError:
                    page.go_back()
                    search_box = parent.locator(".custom-keywordSearchElement")
                    search_box.first.wait_for(state="visible", timeout=60000)
                    search_box.fill(keyword)

                try:
                    old_first_text = parent.locator('[class*="custom-tenderList-"]').first.inner_text(timeout=3000)
                except Exception:
                    old_first_text = None

                submit_btn = parent.locator(".custom-submitButtonElement").first
                submit_btn.wait_for(state="visible", timeout=60000)
                click_and_wait_for_refresh(page, submit_btn, adapter, timeout=60000)

                install_custom_selector_loop(page, adapter)

                result_loaded, got_no_results, reason = wait_for_tender_results_refresh(
                    page, adapter, old_first_card_text=old_first_text
                )

                if got_no_results:
                    continue

                install_custom_selector_loop(page, adapter)
                runMainLogic(
                    page, parent,
                    keyword=keyword,
                    category=keywordIndexes[keywordList.index(category)],
                    adapter=adapter,
                )


# ===========================================================================
# SECTION 5 — THREAD RUNNER + POST-PROCESSING
# ===========================================================================

threads = []
for adapter in adapters:
    thread = threading.Thread(target=scrape_site, args=(adapter,))
    threads.append(thread)
    thread.start()

for thread in threads:
    thread.join(timeout=600)

print("Finished waiting for scraper threads")
print("Collecting Redis tenders...")

all_tenders = []
for key in r.scan_iter("tender:*"):
    if r.type(key) != "string":
        continue
    value = r.get(key)
    if not value:
        continue
    try:
        all_tenders.append(json.loads(value))
    except Exception:
        print(f"Skipping non-JSON key: {key}")

print(f"Tenders collected: {len(all_tenders)}")

if not all_tenders:
    print("No tenders collected — skipping all downstream steps.")
else:
    print("Running Layer 2: Semantic Embedding Filter...")
    OUTPUT_JSON = os.path.join(BASE_DIR, "all_tenders.json")
    semantic_filter(all_tenders, output_file=OUTPUT_JSON)

    print("Compiling Final Excel...")
    with open(OUTPUT_JSON) as f:
        print(f"JSON contains {len(json.load(f))} tenders")

    json_to_excel(
        json_filename=OUTPUT_JSON,
        excel_filename=os.path.join(BASE_DIR, "all_tenders_pipeline.xlsx"),
    )

end_time = time.perf_counter()
print(f"Execution time: {end_time - start_time:.4f} seconds")
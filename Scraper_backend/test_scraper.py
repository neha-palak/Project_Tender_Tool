"""
Scraper for find-tender.service.gov.uk
Extracts structured tender information from individual notice pages.

Usage:
    python find_tender_scraper.py <url>
    python find_tender_scraper.py <url1> <url2> ...
    python find_tender_scraper.py --file urls.txt
    python find_tender_scraper.py --search "keyword" --pages 3

Output: JSON lines written to stdout (one JSON object per tender).
"""

import sys
import re
import json
import time
import argparse
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlencode, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "https://www.find-tender.service.gov.uk"
SEARCH_URL = f"{BASE_URL}/Search/Results"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TenderScraper/1.0; "
        "+https://github.com/example/tender-scraper)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

REQUEST_DELAY = 1.5   # seconds between requests (be polite)
REQUEST_TIMEOUT = 30  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch(session: requests.Session, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            log.warning("Attempt %d/%d failed for %s: %s", attempt + 1, retries, url, exc)
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
    log.error("All retries exhausted for %s", url)
    return None


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    text = text.strip()
    return text if text else None


def text_of(soup, selector: str, **kwargs) -> Optional[str]:
    el = soup.find(selector, **kwargs) if kwargs else soup.select_one(selector)
    return clean(el.get_text(separator=" ", strip=True)) if el else None


def para_texts(soup) -> list[str]:
    """Return all <p class='govuk-body'> text blocks (used for description)."""
    return [p.get_text(strip=True) for p in soup.find_all("p", class_="govuk-body") if p.get_text(strip=True)]


# ---------------------------------------------------------------------------
# Currency / value parsing
# ---------------------------------------------------------------------------

def parse_value(raw: Optional[str]):
    """
    Parse a value string like '£12,000,000' or 'EUR 500,000'.
    Returns (currency_symbol, numeric_value) or (None, None).
    """
    if not raw:
        return None, None
    raw = raw.replace(",", "").replace("\xa0", " ").strip()
    # Patterns: £1234, GBP 1234, EUR 1234, 1234 GBP, Value excluding VAT: £12000
    m = re.search(
        r"(?:Value excluding VAT:\s*)?"
        r"(£|€|\$|GBP|EUR|USD|CAD|AUD)?\s*"
        r"([\d]+(?:\.\d+)?)"
        r"\s*(£|€|\$|GBP|EUR|USD|CAD|AUD)?",
        raw,
        re.IGNORECASE,
    )
    if not m:
        return None, None
    currency = m.group(1) or m.group(3)
    amount = float(m.group(2))
    if currency:
        currency = currency.strip()
    return currency or None, amount


def currency_to_iso(symbol: Optional[str]) -> Optional[str]:
    if not symbol:
        return None
    mapping = {"£": "GBP", "€": "EUR", "$": "USD"}
    return mapping.get(symbol, symbol.upper())


# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------

def extract_tender(soup: BeautifulSoup, url: str) -> dict:
    result = {
        "Budget Currency": None,
        "Budget in Local Currency Minimum": None,
        "Budget in Local Currency Maximum": None,
        "Budget in INR Minimum": None,
        "Budget in INR Maximum": None,
        "Order Quantity": None,
        "Expiry Date": "-",
        "Opening Date": "-",
        "Organisation Name": None,
        "Link to the Tender": url,
        "Tender Title": None,
        "Tender Description": None,
        "Special Observation": None,
        "Award Date": None,
        "Timeline": None,
        "Eligibility": None,
    }

    # ---- Title ----
    h1 = soup.find("h1", class_="govuk-heading-l")
    result["Tender Title"] = clean(h1.get_text(strip=True)) if h1 else None

    # ---- Organisation Name ----
    # The first <ul class="govuk-list"> after the h1 usually contains the org
    org_list = soup.select_one("h1.govuk-heading-l + div ul.govuk-list")
    if org_list:
        li = org_list.find("li")
        result["Organisation Name"] = clean(li.get_text(strip=True)) if li else None

    # Also try Section I contracting authority name (more reliable)
    main = soup.find("main")
    if main:
        # Find "I.1) Name and addresses" section
        auth_heading = main.find(lambda t: t.name in ("h3",) and "Name and addresses" in t.get_text())
        if auth_heading:
            # The org name is the first <p class="govuk-body govuk-!-margin-bottom-0"> after the heading
            for sib in auth_heading.next_siblings:
                if hasattr(sib, "name") and sib.name == "p" and "govuk-body" in sib.get("class", []):
                    org = clean(sib.get_text(strip=True))
                    if org:
                        result["Organisation Name"] = org
                        break

    # ---- Description ----
    # Find the "Short description" section (II.1.4)
    desc_heading = None
    if main:
        for h4 in main.find_all("h4"):
            txt = h4.get_text()
            if "Short description" in txt or "II.1.4" in txt:
                desc_heading = h4
                break

    if desc_heading:
        desc_parts = []
        for sib in desc_heading.next_siblings:
            if hasattr(sib, "name"):
                if sib.name == "p" and "govuk-body" in sib.get("class", []):
                    txt = sib.get_text(strip=True)
                    if txt:
                        desc_parts.append(txt)
                elif sib.name in ("h3", "h4", "h2", "hr"):
                    break
        if desc_parts:
            result["Tender Description"] = "\n".join(desc_parts)

    # If no short description found, try the scope description
    if not result["Tender Description"] and main:
        scope_heading = None
        for h3 in main.find_all("h3"):
            if "Scope" in h3.get_text():
                scope_heading = h3
                break
        if scope_heading:
            desc_parts = []
            for sib in scope_heading.next_siblings:
                if hasattr(sib, "name"):
                    if sib.name == "p" and "govuk-body" in sib.get("class", []):
                        desc_parts.append(sib.get_text(strip=True))
                    elif sib.name in ("h3", "h4", "h2", "hr"):
                        break
            if desc_parts:
                result["Tender Description"] = "\n".join(desc_parts)

    # ---- Budget / Value ----
    # Look for "Estimated total value" (II.1.5)
    value_raw = None
    if main:
        for h4 in main.find_all("h4"):
            if "Estimated total value" in h4.get_text() or "II.1.5" in h4.get_text():
                for sib in h4.next_siblings:
                    if hasattr(sib, "name") and sib.name == "p" and "govuk-body" in sib.get("class", []):
                        value_raw = sib.get_text(strip=True)
                        break
                break

    if value_raw:
        currency_sym, amount = parse_value(value_raw)
        result["Budget Currency"] = currency_to_iso(currency_sym)
        # Single estimated value → use as both min and max
        result["Budget in Local Currency Minimum"] = amount
        result["Budget in Local Currency Maximum"] = amount

    # ---- Dates ----
    if main:
        # Opening date: "Time limit for receipt of tenders" (IV.2.2)
        for h4 in main.find_all("h4"):
            if "Time limit for receipt" in h4.get_text() or "IV.2.2" in h4.get_text():
                date_parts = []
                for sib in h4.next_siblings:
                    if hasattr(sib, "name"):
                        if sib.name == "h5":
                            continue
                        if sib.name == "p" and "govuk-body" in sib.get("class", []):
                            date_parts.append(sib.get_text(strip=True))
                        elif sib.name in ("h3", "h4", "h2", "hr") and date_parts:
                            break
                if date_parts:
                    result["Opening Date"] = " ".join(date_parts[:2])  # date + time
                break

        # Opening of tenders date: (IV.2.7)
        for h4 in main.find_all("h4"):
            if "Conditions for opening" in h4.get_text() or "IV.2.7" in h4.get_text():
                date_parts = []
                for sib in h4.next_siblings:
                    if hasattr(sib, "name"):
                        if sib.name == "h5":
                            continue
                        if sib.name == "p" and "govuk-body" in sib.get("class", []):
                            date_parts.append(sib.get_text(strip=True))
                        elif sib.name in ("h3", "h4", "h2", "hr") and date_parts:
                            break
                if date_parts:
                    result["Expiry Date"] = " ".join(date_parts[:2])
                break

        # Award date: look in Section V (contract award)
        for h4 in main.find_all("h4"):
            if "Date of conclusion" in h4.get_text() or "V.2.1" in h4.get_text():
                for sib in h4.next_siblings:
                    if hasattr(sib, "name") and sib.name == "p" and "govuk-body" in sib.get("class", []):
                        result["Award Date"] = clean(sib.get_text(strip=True))
                        break
                break

    # ---- Eligibility ----
    if main:
        for h4 in main.find_all("h4"):
            if "Economic and financial standing" in h4.get_text() or "III.1.2" in h4.get_text():
                for sib in h4.next_siblings:
                    if hasattr(sib, "name") and sib.name == "p" and "govuk-body" in sib.get("class", []):
                        txt = clean(sib.get_text(strip=True))
                        if txt and txt.lower() not in ("none", "not applicable"):
                            result["Eligibility"] = txt
                        break
                break

    # ---- Timeline (duration) ----
    if main:
        for h5 in main.find_all("h5"):
            if "Duration in months" in h5.get_text():
                for sib in h5.next_siblings:
                    if hasattr(sib, "name") and sib.name == "p" and "govuk-body" in sib.get("class", []):
                        months = clean(sib.get_text(strip=True))
                        if months:
                            result["Timeline"] = f"{months} months"
                        break
                break

    return result


# ---------------------------------------------------------------------------
# Search / listing
# ---------------------------------------------------------------------------

def get_notice_urls_from_search(
    session: requests.Session,
    keyword: str = "",
    pages: int = 1,
) -> list[str]:
    """Crawl search results and return a list of notice URLs."""
    urls = []
    for page in range(1, pages + 1):
        params = {"Keywords": keyword, "Page": page}
        search_url = f"{SEARCH_URL}?{urlencode(params)}"
        log.info("Fetching search page %d: %s", page, search_url)
        soup = fetch(session, search_url)
        if not soup:
            break
        # Each result is a heading link like /Notice/XXXXXX-YYYY
        links = soup.select("a[href^='/Notice/']")
        found = []
        for a in links:
            href = a["href"].split("#")[0].split("?")[0]
            if re.match(r"^/Notice/\d{6}-\d{4}$", href):
                full = urljoin(BASE_URL, href)
                if full not in urls and full not in found:
                    found.append(full)
        if not found:
            log.info("No more results on page %d", page)
            break
        urls.extend(found)
        log.info("Found %d notices on page %d (total so far: %d)", len(found), page, len(urls))
        time.sleep(REQUEST_DELAY)
    return urls


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def scrape_urls(urls: list[str], output_file=None) -> list[dict]:
    session = get_session()
    results = []
    out = open(output_file, "w", encoding="utf-8") if output_file else None

    for i, url in enumerate(urls, 1):
        log.info("[%d/%d] Scraping: %s", i, len(urls), url)
        soup = fetch(session, url)
        if not soup:
            log.warning("Skipping %s (fetch failed)", url)
            continue
        data = extract_tender(soup, url)
        results.append(data)
        line = json.dumps(data, ensure_ascii=False)
        if out:
            out.write(line + "\n")
            out.flush()
        else:
            print(line)
        if i < len(urls):
            time.sleep(REQUEST_DELAY)

    if out:
        out.close()
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Scrape tender data from find-tender.service.gov.uk",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("urls", nargs="*", help="One or more notice URLs to scrape")
    parser.add_argument("--file", "-f", help="Text file with one URL per line")
    parser.add_argument("--search", "-s", help="Search keyword to find tenders")
    parser.add_argument(
        "--pages", "-p", type=int, default=1,
        help="Number of search result pages to crawl (default: 1)"
    )
    parser.add_argument(
        "--output", "-o", help="Write results to this JSON-lines file (default: stdout)"
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print JSON output (only useful with --output)"
    )
    args = parser.parse_args()

    urls = list(args.urls)

    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            for line in fh:
                u = line.strip()
                if u and not u.startswith("#"):
                    urls.append(u)

    if args.search:
        session = get_session()
        found = get_notice_urls_from_search(session, args.search, args.pages)
        urls.extend(found)

    if not urls:
        parser.error(
            "Provide at least one URL, a --file of URLs, or use --search to find tenders."
        )

    urls = list(dict.fromkeys(urls))  # deduplicate, preserve order
    log.info("Total URLs to scrape: %d", len(urls))

    results = scrape_urls(urls, output_file=args.output if not args.pretty else None)

    if args.output and args.pretty:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
        log.info("Results written to %s", args.output)
    elif args.output:
        log.info("Results written to %s", args.output)


if __name__ == "__main__":
    main()
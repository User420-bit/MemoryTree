"""
Responsive design verification for Memory Tree.
Tests all pages across multiple viewports for horizontal overflow,
element collisions, and content visibility.
"""

import json
import os
import sys
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("MT_TEST_BASE_URL", "http://localhost:8000")
USERNAME = os.environ.get("MT_TEST_USERNAME", "partner_a")
# Kein Default-Passwort im Source: Wert kommt ausschließlich aus der Umgebung.
# Für lokale Dev-Runs: export MT_TEST_PASSWORD=...  (oder in einer .env)
PASSWORD = os.environ.get("MT_TEST_PASSWORD", "")  # noqa: S105 - aus Env

# Viewport matrix: name → (width, height)
VIEWPORTS = {
    "iPhone SE (320)":   (320, 568),
    "iPhone 12 (390)":   (390, 844),
    "iPad Mini (768)":   (768, 1024),
    "iPad Air (820)":    (820, 1180),
    "iPad Pro (1024)":   (1024, 1366),
    "Laptop (1280)":     (1280, 800),
    "Desktop (1440)":    (1440, 900),
}

# Pages to test (after login)
PAGES = [
    ("/", "Dashboard"),
    ("/tree", "Baum"),
    ("/timeline", "Timeline"),
    ("/map", "Karte"),
    ("/gallery", "Galerie"),
    ("/milestones", "Meilensteine"),
    ("/settings", "Einstellungen"),
]


def login(page):
    """Login and return True if successful."""
    page.goto(f"{BASE_URL}/auth/login", wait_until="networkidle")
    page.fill('input[name="username"]', USERNAME)
    page.fill('input[name="password"]', PASSWORD)
    page.click('form [type="submit"]')
    page.wait_for_load_state("networkidle")
    # Check we're not still on login page
    return "/auth/login" not in page.url


def check_horizontal_overflow(page, viewport_name, page_name):
    """Check if any element extends beyond viewport width."""
    results = page.evaluate("""() => {
        const vw = document.documentElement.clientWidth;
        const problems = [];
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const rect = el.getBoundingClientRect();
            // Element extends beyond right edge
            if (rect.right > vw + 2) {  // 2px tolerance
                const tag = el.tagName.toLowerCase();
                const cls = el.className ? (typeof el.className === 'string' ? el.className.slice(0, 80) : '') : '';
                const id = el.id || '';
                problems.push({
                    tag: tag,
                    id: id,
                    class: cls,
                    right: Math.round(rect.right),
                    width: Math.round(rect.width),
                    viewport: vw,
                    overflow: Math.round(rect.right - vw)
                });
            }
            // Element extends beyond left edge
            if (rect.left < -2) {
                const tag = el.tagName.toLowerCase();
                const cls = el.className ? (typeof el.className === 'string' ? el.className.slice(0, 80) : '') : '';
                const id = el.id || '';
                problems.push({
                    tag: tag,
                    id: id,
                    class: cls,
                    left: Math.round(rect.left),
                    width: Math.round(rect.width),
                    viewport: vw,
                    overflow: Math.round(-rect.left)
                });
            }
        }
        return problems;
    }""")
    return results


def check_body_scroll(page):
    """Check if body has horizontal scrollbar."""
    return page.evaluate("""() => {
        return {
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            hasHScroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
        };
    }""")


def check_text_truncation(page):
    """Check for text that's completely invisible due to overflow:hidden.
    Excludes elements inside hidden containers (mobile menus, etc.)."""
    return page.evaluate("""() => {
        const problems = [];
        const textEls = document.querySelectorAll('h1, h2, h3, h4, p, span, a, button, label, td, th, li');
        for (const el of textEls) {
            const text = el.textContent?.trim();
            if (!text || text.length < 3) continue;
            const rect = el.getBoundingClientRect();
            // Element has content but zero visible area
            if (rect.width < 1 || rect.height < 1) {
                const style = getComputedStyle(el);
                if (style.display !== 'none' && style.visibility !== 'hidden') {
                    // Check if ANY ancestor has display:none or hidden class
                    // (e.g. mobile menu, hamburger toggle content)
                    let ancestor = el.parentElement;
                    let hiddenByParent = false;
                    while (ancestor && ancestor !== document.body) {
                        const aStyle = getComputedStyle(ancestor);
                        if (aStyle.display === 'none' || aStyle.visibility === 'hidden') {
                            hiddenByParent = true;
                            break;
                        }
                        // Also check for Tailwind 'hidden' class
                        if (ancestor.classList.contains('hidden')) {
                            hiddenByParent = true;
                            break;
                        }
                        ancestor = ancestor.parentElement;
                    }
                    if (!hiddenByParent) {
                        problems.push({
                            tag: el.tagName.toLowerCase(),
                            text: text.slice(0, 50),
                            width: rect.width,
                            height: rect.height
                        });
                    }
                }
            }
        }
        return problems;
    }""")


def check_element_overlaps(page):
    """Check for significant overlaps between sibling nav/header elements.
    Only checks actual siblings, not parent-child relationships."""
    return page.evaluate("""() => {
        const problems = [];
        // Check navbar items specifically — only direct children of the same container
        const containers = document.querySelectorAll('nav > div > div, header > div > div');
        for (const container of containers) {
            const items = Array.from(container.children).filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            });
            const rects = items.map(el => ({
                el: el.tagName + (el.className ? '.' + (typeof el.className === 'string' ? el.className.split(' ')[0] : '') : ''),
                text: (el.textContent || '').trim().slice(0, 30),
                left: el.getBoundingClientRect().left,
                right: el.getBoundingClientRect().right,
                top: el.getBoundingClientRect().top,
                bottom: el.getBoundingClientRect().bottom,
                height: el.getBoundingClientRect().height
            }));
            for (let i = 0; i < rects.length; i++) {
                for (let j = i + 1; j < rects.length; j++) {
                    const a = rects[i], b = rects[j];
                    // Same vertical band
                    if (Math.abs(a.top - b.top) < a.height * 0.5) {
                        const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
                        if (overlapX > 5) {
                            problems.push({
                                el1: a.text || a.el,
                                el2: b.text || b.el,
                                overlapPx: Math.round(overlapX)
                            });
                        }
                    }
                }
            }
        }
        return problems;
    }""")


def _check_http_status(resp, vp_name, page_name):
    """Return an issue dict if response is an HTTP error, else None."""
    if resp and resp.status >= 400:
        return {
            "viewport": vp_name,
            "page": page_name,
            "type": "HTTP_ERROR",
            "detail": f"Status {resp.status}",
        }
    return None


def _check_scroll_issue(page, vp_name, page_name):
    scroll = check_body_scroll(page)
    if not scroll["hasHScroll"]:
        return None
    return {
        "viewport": vp_name,
        "page": page_name,
        "type": "HORIZONTAL_SCROLL",
        "detail": f"scrollWidth={scroll['scrollWidth']} > clientWidth={scroll['clientWidth']}",
    }


def _filter_significant_overflows(overflows):
    return [
        o for o in overflows
        if o.get("overflow", 0) > 10
        and "hidden" not in o.get("class", "")
        and "leaflet-" not in o.get("class", "")
    ]


def _collect_overflow_issues(page, vp_name, page_name):
    overflows = check_horizontal_overflow(page, vp_name, page_name)
    significant = _filter_significant_overflows(overflows)
    if not significant:
        return []
    seen = set()
    issues = []
    for o in significant[:10]:
        key = f"{o['tag']}.{o.get('class','')[:30]}"
        if key in seen:
            continue
        seen.add(key)
        issues.append({
            "viewport": vp_name,
            "page": page_name,
            "type": "ELEMENT_OVERFLOW",
            "detail": (
                f"<{o['tag']}> class='{o.get('class','')[:60]}' "
                f"overflows by {o['overflow']}px "
                f"(right={o.get('right','?')}, vw={o['viewport']})"
            ),
        })
    return issues


def _collect_truncation_issues(page, vp_name, page_name):
    return [
        {
            "viewport": vp_name,
            "page": page_name,
            "type": "TEXT_INVISIBLE",
            "detail": f"<{t['tag']}> text='{t['text']}' has {t['width']}x{t['height']} size",
        }
        for t in check_text_truncation(page)[:5]
    ]


def _collect_overlap_issues(page, vp_name, page_name):
    return [
        {
            "viewport": vp_name,
            "page": page_name,
            "type": "ELEMENT_OVERLAP",
            "detail": f"'{ol['el1']}' overlaps '{ol['el2']}' by {ol['overlapPx']}px",
        }
        for ol in check_element_overlaps(page)[:5]
    ]


def _test_single_page(page, path, page_name, vp_name):
    """Run all checks for one page; return list of issue dicts."""
    try:
        resp = page.goto(f"{BASE_URL}{path}", wait_until="networkidle", timeout=15000)
    except Exception as exc:
        return [{
            "viewport": vp_name,
            "page": page_name,
            "type": "ERROR",
            "detail": str(exc)[:200],
        }]

    http_issue = _check_http_status(resp, vp_name, page_name)
    if http_issue:
        return [http_issue]

    page.wait_for_timeout(500)
    issues = []
    scroll_issue = _check_scroll_issue(page, vp_name, page_name)
    if scroll_issue:
        issues.append(scroll_issue)
    issues.extend(_collect_overflow_issues(page, vp_name, page_name))
    issues.extend(_collect_truncation_issues(page, vp_name, page_name))
    issues.extend(_collect_overlap_issues(page, vp_name, page_name))
    return issues


def _test_viewport(browser, vp_name, width, height):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    issues = []
    if not login(page):
        issues.append({
            "viewport": vp_name,
            "page": "Login",
            "type": "LOGIN_FAILED",
            "detail": f"Could not login at {width}x{height}",
        })
        context.close()
        return issues

    page.goto(f"{BASE_URL}/auth/login", wait_until="networkidle")
    for path, page_name in PAGES:
        issues.extend(_test_single_page(page, path, page_name, vp_name))
    context.close()
    return issues


def run_tests():
    issues = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp_name, (w, h) in VIEWPORTS.items():
            issues.extend(_test_viewport(browser, vp_name, w, h))
        browser.close()
    return issues


if __name__ == "__main__":
    print("=" * 70)
    print("Memory Tree — Responsive Design Test")
    print("=" * 70)
    
    issues = run_tests()
    
    if not issues:
        print("\n✅ ALL TESTS PASSED — No responsive issues detected!")
    else:
        print(f"\n⚠️  Found {len(issues)} issue(s):\n")
        
        # Group by type
        by_type = {}
        for issue in issues:
            t = issue["type"]
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(issue)
        
        for issue_type, items in by_type.items():
            print(f"\n{'─' * 50}")
            print(f"  {issue_type} ({len(items)} issues)")
            print(f"{'─' * 50}")
            for item in items:
                print(f"  [{item['viewport']}] {item['page']}: {item['detail']}")
    
    # Write JSON report
    with open("tests/responsive_report.json", "w") as f:
        json.dump(issues, f, indent=2, ensure_ascii=False)
    print("\nFull report: tests/responsive_report.json")
    
    sys.exit(1 if issues else 0)

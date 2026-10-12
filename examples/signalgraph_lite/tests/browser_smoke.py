import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description='Browser smoke checks against a running offline demo.')
parser.add_argument('--url', default='http://127.0.0.1:8765')
parser.add_argument('--artifacts', type=Path, default=Path('work/signalgraph-captures'))
args = parser.parse_args()
args.artifacts.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.environ.get('CHROMIUM_EXECUTABLE'), headless=True
    )
    page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(args.url)
    page.locator('#app').wait_for(state='visible')
    page.screenshot(path=str(args.artifacts / 'overview.png'), full_page=True)
    print('counts', page.locator('.metric strong').all_text_contents())
    page.locator('nav [data-view="changes"]').click()
    page.select_option('#kind-filter', 'conflict')
    assert page.locator('#changes-list .event-row').count() == 2
    page.locator('#changes-list .event-row').first.click()
    assert page.locator('#evidence').is_visible()
    assert (
        's03' in page.locator('#evidence-body').inner_text()
        and 's08' in page.locator('#evidence-body').inner_text()
    )
    page.screenshot(path=str(args.artifacts / 'evidence.png'), full_page=True)
    page.keyboard.press('Escape')
    assert not page.locator('#evidence').is_visible()
    assert page.locator('#changes-list .event-row').first.evaluate(
        '(element) => element === document.activeElement'
    )
    page.fill('#search', 'doesnotexist')
    assert 'No matching detections' in page.locator('#changes-list').inner_text()
    page.locator('#changes-list [data-reset]').click()
    assert page.locator('#changes-list .event-row').count() == 8
    page.select_option('#entity-filter', 'helios')
    assert page.locator('#changes-list .event-row').count() == 1
    page.select_option('#entity-filter', 'all')
    page.locator('nav [data-view="timeline"]').click()
    assert page.locator('.timeline-day').count() == 12
    page.locator('#date-range').fill('0')
    assert page.locator('.timeline-day').count() == 1
    page.locator('nav [data-view="entities"]').click()
    page.locator('#entity-list [data-entity="aster"]').click()
    assert page.locator('.relationship').count() == 3
    page.locator('#entity-list [data-entity="nova-energy"]').click()
    assert 'USD 8m' in page.locator('#entity-detail').inner_text()
    page.locator('nav [data-view="sources"]').click()
    assert page.locator('.source-card').count() == 12
    page.locator('.source-card [data-source="s01"]').click()
    assert 'fixture://announcements/s01' in page.locator('#evidence-body').inner_text()
    page.keyboard.press('Escape')
    with page.expect_download() as download:
        page.locator('#export').click()
    payload = json.loads(Path(download.value.path()).read_text())
    assert payload['counts']['conflict'] == 2
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(args.url + '/#overview')
    page.locator('#app').wait_for(state='visible')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(args.artifacts / 'mobile.png'), full_page=True)
    page.locator('#priority-list .event-row').first.click()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.keyboard.press('Escape')
    page.route(
        '**/api/snapshot*',
        lambda route: route.fulfill(
            status=500, content_type='application/json', body='{"error":"test failure"}'
        ),
    )
    page.reload()
    page.locator('[data-retry]').wait_for(state='visible')
    assert 'HTTP 500' in page.locator('#state').inner_text()
    page.unroute('**/api/snapshot*')
    page.locator('[data-retry]').click()
    page.locator('#app').wait_for(state='visible')
    assert not errors, errors
    print(
        'Browser checks passed: navigation, filters, evidence, Escape/focus, timeline, entities, sources, export, mobile overflow, error retry.'
    )
    # Empty state is explicit and has a recovery control.
    page.route(
        '**/api/snapshot*',
        lambda route: route.fulfill(
            status=200,
            content_type='application/json',
            body=json.dumps(
                {'mode': 'offline-demo', 'events': [], 'documents': [], 'entities': []}
            ),
        ),
    )
    page.reload()
    page.locator('[data-retry]').wait_for(state='visible')
    assert 'No investigation data' in page.locator('#state').inner_text()
    browser.close()

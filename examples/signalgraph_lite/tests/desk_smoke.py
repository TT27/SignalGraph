"""Disposable end-to-end investigation: imports, two clocks, reviews, watches, graph, exports."""

import argparse
import json
import os
import sys
import tempfile
import threading
from dataclasses import asdict
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root))
    from examples.signalgraph_lite.engine import load_dataset
    from examples.signalgraph_lite.server import handler_for
    from examples.signalgraph_lite.store import WorkspaceStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, default=Path('work/desk-captures'))
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        store = WorkspaceStore(Path(temp) / 'test.sqlite3')
        handler = handler_for(store)
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE'))
                page = browser.new_page(viewport={'width': 1440, 'height': 1080})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#app').wait_for(state='visible')
                page.locator('#replay-summary').filter(has_text='12 known documents').wait_for(
                    state='attached'
                )
                page.screenshot(path=str(args.artifacts / 'overview.png'), full_page=True)
                assert page.locator('.metric strong').all_text_contents() == ['12', '6', '4', '2']

                # Observation time prevents knowledge of a later publication.
                page.locator('nav [data-view="replay"]').click()
                page.locator('#observed-slider').fill('4')
                page.locator('#replay-summary').filter(has_text='5 known documents').wait_for()
                assert not page.locator('#replay-rows').filter(has_text='150').count()
                page.locator('#observed-slider').fill('11')
                page.locator('#replay-summary').filter(has_text='12 known documents').wait_for()
                page.locator('#valid-date').fill('2026-01-20')
                page.locator('#valid-date').dispatch_event('change')
                page.locator('#replay-rows tr').filter(has_text='150').filter(
                    has_text='future'
                ).wait_for()
                page.screenshot(path=str(args.artifacts / 'replay.png'), full_page=True)
                page.locator('#valid-date').fill('2026-02-12')
                page.locator('#valid-date').dispatch_event('change')
                page.locator('#replay-rows tr').filter(has_text='150').filter(
                    has_text='active'
                ).wait_for()

                page.locator('nav [data-view="graph"]').click()
                page.locator('.graph-node').first.wait_for(state='visible')
                assert page.locator('.graph-node').count() == 6
                page.locator('[data-graph-node="aster"]').focus()
                page.keyboard.press('Enter')
                assert 'Helios Systems' in page.locator('#graph-detail').inner_text()
                page.screenshot(path=str(args.artifacts / 'graph.png'), full_page=True)
                assert page.locator('.graph-edge').count() == 3
                page.select_option('#graph-scope', 'active')
                assert page.locator('.graph-edge').count() == 0

                # Annotate a conflict; the original detection and both excerpts remain.
                page.locator('nav [data-view="changes"]').click()
                page.select_option('#kind-filter', 'conflict')
                page.locator('#changes-list .event-row').first.click()
                assert page.locator('.diff-box ins').count() > 0
                page.select_option('#review-status', 'resolved')
                page.fill(
                    '#review-note',
                    'Confirmed conflicting announcements; awaiting publisher correction.',
                )
                page.locator('#review-form button[type="submit"]').click()
                page.locator('.review-editor').filter(has_text='VERSION 1').wait_for()
                page.screenshot(path=str(args.artifacts / 'evidence.png'), full_page=True)
                page.keyboard.press('Escape')
                page.locator('nav [data-view="board"]').click()
                assert page.locator('.board-column').filter(has_text='RESOLVED / 1').count() == 1
                page.reload()
                page.locator('#app').wait_for(state='visible')
                assert page.locator('.board-column').filter(has_text='RESOLVED / 1').count() == 1
                assert page.locator('.metric strong').last.inner_text() == '2'

                page.locator('nav [data-view="watches"]').click()
                page.fill('#watch-label', 'Revenue conflict watch')
                page.select_option('#watch-entity', 'helios')
                page.locator('#watch-form button[type="submit"]').click()
                page.locator('.alert-card').filter(has_text='Revenue conflict watch').wait_for()
                assert page.locator('.alert-card').count() == 1
                page.locator('[data-ack-watch]').click()
                page.locator('.alert-card').filter(has_text='Acknowledged').wait_for()
                page.reload()
                page.locator('#app').wait_for(state='visible')
                assert page.locator('.alert-card').count() == 1
                assert 'Acknowledged' in page.locator('#alert-list').inner_text()
                page.screenshot(path=str(args.artifacts / 'watches.png'), full_page=True)

                with page.expect_download() as download:
                    page.locator('#download-briefing').click()
                text = Path(download.value.path()).read_text()
                assert 'SHA-256' in text and 'awaiting publisher correction' in text

                # Invalid imports expose a useful error and create no partial investigation.
                page.locator('#open-import').click()
                bad = json.loads(json.dumps(asdict(load_dataset())))
                bad['claims'][0]['quote'] = 'Invented citation'
                page.fill('#import-json', json.dumps(bad))
                page.locator('#import-form button[type="submit"]').click()
                page.locator('#import-status').filter(has_text='exact source excerpt').wait_for()
                assert len(store.list_workspaces()) == 1
                imported = json.loads(json.dumps(asdict(load_dataset())))
                for doc in imported['documents']:
                    doc['synthetic'] = False
                page.fill('#import-name', 'Supplier due diligence')
                page.fill('#import-json', json.dumps(imported))
                page.locator('#import-form button[type="submit"]').click()
                page.locator('#data-label').filter(has_text='IMPORTED EVIDENCE').wait_for()
                assert len(store.list_workspaces()) == 2
                workspace = page.locator('#workspace-select').input_value()
                assert workspace != 'demo'
                assert not store.view(workspace)['history']
                page.reload()
                page.locator('#app').wait_for(state='visible')
                assert page.locator('#workspace-select').input_value() == workspace
                assert page.locator('#data-label').inner_text() == 'IMPORTED EVIDENCE'
                page.locator('#open-import').click()
                page.select_option('#import-action', 'append')
                page.fill('#import-json', json.dumps(imported))
                page.locator('#import-form button[type="submit"]').click()
                page.locator('#import-dialog').wait_for(state='hidden')
                assert len(store.dataset(workspace).documents) == 12

                page.select_option('#workspace-select', 'demo')
                page.locator('#data-label').filter(has_text='SYNTHETIC DATA').wait_for()
                page.set_viewport_size({'width': 390, 'height': 844})
                page.goto(f'http://127.0.0.1:{server.server_port}/#overview')
                page.locator('#app').wait_for(state='visible')
                page.screenshot(path=str(args.artifacts / 'mobile.png'), full_page=True)
                for view in ('overview', 'replay', 'graph', 'board', 'watches'):
                    page.locator(f'nav [data-view="{view}"]').click()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), view
                assert not errors, errors
                browser.close()
                print(
                    'Desk browser checks passed: import validation, isolated investigations, append, persistence, two-clock replay, graph, review history, watch inbox, briefing export, mobile.'
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()

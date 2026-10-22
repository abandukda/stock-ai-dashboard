"""Generated component renders; not production or genuine signal evidence."""
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright
from ui.report_card_overview import DIRECTORY_CSS, signal_directory_html


class RegistrationRenderTest(unittest.TestCase):
    def test_registration_and_reference_remain_distinct_at_all_viewports(self):
        root = Path('audit_results/premium_home/report_card_registration')
        root.mkdir(parents=True, exist_ok=True)
        signal = dict(signal_id='GENERATED_ONLY', ticker='SYNTHETIC',
                      registered_at='2026-10-08T03:20:18Z',
                      signal_timestamp='2026-10-06T00:00:00Z',
                      reference_price=None, reference_price_timestamp=None,
                      observation_count=0)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for width in (360, 768, 1440):
                    page = browser.new_page(viewport={'width': width, 'height': 1000})
                    page.route('**/*', lambda route: route.abort())
                    page.set_content('<body style="background:#0a1423;font-family:Arial;padding:12px">'
                        '<p style="color:white">GENERATED COMPONENT — NOT PRODUCTION</p>'
                        + DIRECTORY_CSS + signal_directory_html([signal]) + '</body>')
                    self.assertEqual(page.locator('tbody tr').count(), 1)
                    self.assertIn('Oct 08, 2026 03:20:18 UTC', page.locator('tbody').inner_text())
                    self.assertIn('Oct 06, 2026', page.locator('tbody').inner_text())
                    self.assertIn('not proof of customer publication', page.locator('body').inner_text())
                    self.assertNotIn('0%', page.locator('body').inner_text())
                    self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                    page.screenshot(path=str(root / f'GENERATED_NOT_PRODUCTION_registration_{width}.png'), full_page=True)
                    page.close()
            finally:
                browser.close()

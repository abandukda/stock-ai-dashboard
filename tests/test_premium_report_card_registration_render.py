"""Generated component renders; not production or genuine signal evidence."""
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright
from ui.report_card_overview import DIRECTORY_CSS, OVERVIEW_CSS, overview_html, signal_directory_html


class RegistrationRenderTest(unittest.TestCase):
    def test_missing_observations_do_not_render_available_performance(self):
        root = Path('audit_results/premium_home/report_card_registration')
        root.mkdir(parents=True, exist_ok=True)
        report = dict(signal_count=20, observation_count=3, open_signal_count=20,
                      spy_comparison_count=0, rows=[dict(status='MISSING_PRICE')])
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for width in (360, 768, 1440):
                    page = browser.new_page(viewport={'width': width, 'height': 1000})
                    page.route('**/*', lambda route: route.abort())
                    page.set_content('<body style="background:#0a1423;font-family:Arial;padding:12px">'
                        '<p style="color:white">GENERATED COMPONENT — NOT PRODUCTION</p>'
                        + OVERVIEW_CSS + overview_html(report) + '</body>')
                    self.assertEqual(page.locator('.atlas-rc-metrics article').count(), 5)
                    self.assertEqual(page.locator('.atlas-rc-metrics article').last.locator('strong').inner_text(), 'Unavailable')
                    self.assertTrue(page.get_by_text('Performance comparison unavailable', exact=True).is_visible())
                    self.assertNotIn('Recorded evidence is available', page.locator('body').inner_text())
                    self.assertNotIn('0%', page.locator('body').inner_text())
                    self.assertTrue(page.locator('.atlas-rc-metrics article').last.evaluate('''card => {
                        const value = card.querySelector('strong');
                        return value.scrollWidth <= value.clientWidth;
                    }'''))
                    self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                    page.screenshot(path=str(root / f'GENERATED_NOT_PRODUCTION_unavailable_{width}.png'), full_page=True)
                    page.close()
            finally:
                browser.close()

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
                    registration = page.locator('tbody td[title]')
                    self.assertEqual(registration.count(), 1)
                    self.assertEqual(registration.inner_text(), 'Oct 08, 2026')
                    self.assertEqual(registration.get_attribute('title'), 'Oct 08, 2026 03:20:18 UTC')
                    self.assertIn('Oct 06, 2026', page.locator('tbody').inner_text())
                    self.assertIn('not proof of customer publication', page.locator('body').inner_text())
                    self.assertNotIn('0%', page.locator('body').inner_text())
                    self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                    page.screenshot(path=str(root / f'GENERATED_NOT_PRODUCTION_registration_{width}.png'), full_page=True)
                    page.close()
            finally:
                browser.close()

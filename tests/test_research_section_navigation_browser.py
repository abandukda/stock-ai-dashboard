"""Actual browser behavior of the presentation component; GENERATED, not live QA."""
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright
from ui.research_reference_components import (
    RESEARCH_REFERENCE_CSS, RESEARCH_SECTION_LINKS, research_section_navigation_html,
)

class ResearchSectionNavigationBrowser(unittest.TestCase):
    def test_real_component_navigation_at_desktop_tablet_mobile(self):
        output=Path('audit_results/research_section_navigation');output.mkdir(parents=True,exist_ok=True)
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch()
            try:
                for width in (360,768,1440):
                    with self.subTest(width=width):
                        page=browser.new_page(viewport={"width":width,"height":850})
                        page.route('**/*',lambda route:route.abort())
                        sections=''.join(f'<section id="atlas-research-{key}" style="min-height:900px"><h2>{label}</h2><p>Generated navigation target; no financial evidence.</p></section>' for key,label in RESEARCH_SECTION_LINKS)
                        page.set_content('<!doctype html><meta charset="utf-8">'+RESEARCH_REFERENCE_CSS+
                            '<style>body{margin:16px;background:#07111f;color:#eef6ff;font-family:Arial}nav{max-width:100%}*{box-sizing:border-box}</style>'+
                            '<h1>GENERATED COMPONENT QA — NOT PRODUCTION</h1>'+research_section_navigation_html()+sections)
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                        links=page.locator('nav a')
                        self.assertEqual(links.count(),9)
                        for index in range(links.count()):
                            box=links.nth(index).bounding_box()
                            self.assertGreaterEqual(box['height'],44)
                            href=links.nth(index).get_attribute('href')
                            self.assertEqual(page.locator(href).count(),1)
                        page.keyboard.press('Tab')
                        self.assertEqual(page.evaluate('document.activeElement.textContent'),'Overview')
                        for _ in range(8):page.keyboard.press('Tab')
                        self.assertEqual(page.evaluate('document.activeElement.textContent'),'Company')
                        links.nth(8).click()
                        self.assertGreater(page.evaluate('window.scrollY'),1500)
                        self.assertLess(abs(page.locator('#atlas-research-company').bounding_box()['y']),100)
                        page.evaluate('window.scrollTo(0,0)')
                        page.screenshot(path=str(output/f'GENERATED_SECTION_NAV_{width}.png'),full_page=False)
                        page.close()
            finally:browser.close()

if __name__=='__main__':unittest.main()

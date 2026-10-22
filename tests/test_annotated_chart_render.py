"""Real Chromium rendering of a clearly labeled generated fixture, never live evidence."""
from datetime import date,timedelta
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright
from services.annotated_research_chart import build_annotated_research_chart


class AnnotatedChartRender(unittest.TestCase):
    def test_chart_labels_and_panels_at_mobile_tablet_desktop(self):
        source=[{'date':str(date(2026,1,1)+timedelta(days=i)), 'close':100+i*.3,
                 'open':100+i*.3-.2,'high':101+i*.3,'low':99+i*.3,'volume':1000+i*10} for i in range(80)]
        fig,meta=build_annotated_research_chart(source,ticker='GENERATED FIXTURE',
                                             levels=[('Support',100,'dot'),('Resistance',125,'dot')])
        target=Path('audit_results/annotated_chart');target.mkdir(parents=True,exist_ok=True)
        document='<meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:8px;background:#08111f;color:#e2e8f0;font:14px sans-serif}h1{font-size:16px}</style><h1>GENERATED FIXTURE — NOT MARKET DATA OR PRODUCTION QA</h1>'+fig.to_html(full_html=False,include_plotlyjs=True,config={'responsive':True,'displayModeBar':False})
        (target/'generated_fixture.html').write_text(document)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                for width in [360,768,1440]:
                    page=browser.new_page(viewport={'width':width,'height':1040})
                    page.set_content(document)
                    page.wait_for_selector('.main-svg .annotation-text')
                    texts=page.locator('.annotation-text').all_text_contents()
                    self.assertIn('Support · $100.00',texts)
                    self.assertIn('Resistance · $125.00',texts)
                    self.assertTrue(page.locator('.y4title').count())
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                    # Labels must exist and fit, not merely occur in serialized Plotly JSON.
                    for text in ['Support · $100.00','Resistance · $125.00']:
                        box=page.get_by_text(text,exact=True).bounding_box()
                        self.assertIsNotNone(box)
                        self.assertGreaterEqual(box['x'],0)
                        self.assertLessEqual(box['x']+box['width'],width+1)
                    page.screenshot(path=str(target/f'GENERATED_FIXTURE_{width}.png'),full_page=True)
                    page.close()
            finally:browser.close()

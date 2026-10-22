"""Real Chromium geometry regression for clipped production customer navigation."""
import ast
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright
from services.customer_navigation_styles import customer_mobile_navigation_css

ROOT=Path(__file__).resolve().parents[1]

def existing_nav_css():
    tree=ast.parse((ROOT/'app.py').read_text())
    func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='v784_top_nav')
    return next(n.value for n in ast.walk(func) if isinstance(n,ast.Constant) and isinstance(n.value,str) and '@media(max-width:420px)' in n.value)

class CustomerNavGeometry(unittest.TestCase):
    def test_all_labels_fit_at_three_mobile_widths_and_desktop(self):
        labels=['Home','Research','Watchlist','Ask ATLAS']
        baseline='''<style>body{margin:12px} [data-testid="stRadio"]{width:100%}
        label{display:flex;padding:8px 12px;border:1px solid white;font:14px Arial}
        label p{margin:0} </style>'''
        markup='<div data-testid="stRadio"><div role="radiogroup">'+''.join(f'<label><p>{s}</p></label>' for s in labels)+'</div></div>'
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                for width in [360,390,420,1280]:
                    page=browser.new_page(viewport={'width':width,'height':800})
                    page.set_content(baseline+existing_nav_css()+customer_mobile_navigation_css()+markup)
                    values=page.locator('label').evaluate_all('''es=>es.map(e=>{const r=e.getBoundingClientRect();const p=e.querySelector('p');const pr=p.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,text:p.textContent,overflow:p.scrollWidth>p.clientWidth+1,textRight:pr.right}})''')
                    self.assertEqual([v['text'] for v in values],labels)
                    self.assertTrue(all(v['left']>=0 and v['right']<=width and not v['overflow'] and v['textRight']<=v['right'] for v in values),values)
                    self.assertEqual(len({round(v['top']) for v in values}),2 if width<=420 else 1)
                    page.close()
            finally: browser.close()

from html.parser import HTMLParser
from pathlib import Path
import ast
from ui.research_reference_components import RESEARCH_SECTION_LINKS, research_section_navigation_html

class Links(HTMLParser):
    def __init__(self): super().__init__(); self.targets=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a': self.targets.append(dict(attrs)['href'])

def test_all_nine_navigation_links_resolve_to_real_rendered_section_targets():
    nav=Links();nav.feed(research_section_navigation_html())
    source=Path('ui/customer_research_v2.py').read_text()
    tree=ast.parse(source)
    anchor_html=[node.value for node in ast.walk(tree) if isinstance(node,ast.Constant)
                 and isinstance(node.value,str) and '<div id="atlas-research-' in node.value]
    for href in nav.targets:
        assert sum(f'id="{href[1:]}"' in html for html in anchor_html)==1
    assert len(nav.targets)==len(set(nav.targets))==9
    assert {'#atlas-research-statements','#atlas-research-earnings','#atlas-research-news','#atlas-research-company'}<=set(nav.targets)

def test_navigation_is_presentation_only_without_new_sources_or_routes():
    html=research_section_navigation_html()
    assert 'aria-label="Research sections"' in html
    assert 'data-atlas-qa="research-section-navigation"' in html
    assert 'Report Card' not in html and 'href="http' not in html

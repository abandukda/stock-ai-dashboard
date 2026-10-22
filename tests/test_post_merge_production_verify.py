import asyncio
import tempfile
from pathlib import Path
import unittest
import yaml
from scripts.wait_for_production_source import decision, wait

A, B, C = 'a'*40, 'b'*40, 'c'*40
class PostMergeVerification(unittest.TestCase):
    def test_only_known_prior_sha_may_retry(self):
        for sha, classification, expected in [(A,'PASS','READY'),(B,'DEPLOYMENT_NOT_READY','PROPAGATING'),(C,'DEPLOYMENT_NOT_READY','SOURCE_OR_APPLICATION_ERROR'),('UNKNOWN','IN_PROGRESS','SOURCE_OR_APPLICATION_ERROR'),(A,'DEPLOYMENT_DEFECT','SOURCE_OR_APPLICATION_ERROR')]:
            self.assertEqual(decision({'deployed_source_sha':sha,'classification':classification},A,B),expected)
        self.assertEqual(decision({'fatal_exception':True},A,B),'APPLICATION_ERROR')
        self.assertEqual(decision({},'invalid',B),'INVALID_EXPECTED_SOURCE')
    def test_retry_bound_and_no_retry_after_error(self):
        async def run(states, attempts=3):
            calls=[]; pauses=[]
            async def probe():
                value=states[min(len(calls),len(states)-1)];calls.append(value);return value
            async def pause(seconds): pauses.append(seconds)
            with tempfile.TemporaryDirectory() as tmp:
                try: await wait(A,B,Path(tmp)/'receipt.json',probe=probe,pause=pause,attempts=attempts)
                except RuntimeError as error: return str(error),len(calls),len(pauses)
            return 'PASS',len(calls),len(pauses)
        old={'deployed_source_sha':B,'classification':'DEPLOYMENT_NOT_READY'}
        ready={'deployed_source_sha':A,'classification':'PASS'}
        self.assertEqual(asyncio.run(run([old,ready])),('PASS',2,1))
        self.assertEqual(asyncio.run(run([old])),('PROPAGATION_TIMEOUT',3,2))
        self.assertEqual(asyncio.run(run([{'fatal_exception':True}])),('APPLICATION_ERROR',1,0))
    def test_workflow_is_push_only_hosted_and_separates_issue_token(self):
        root=Path(__file__).resolve().parents[1]
        doc=yaml.load((root/'.github/workflows/atlas_post_merge_production_verify.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(set(doc['on']),{'push'})
        self.assertEqual(doc['on']['push']['branches'],['main'])
        verify=doc['jobs']['verify'];report=doc['jobs']['report']
        self.assertEqual(verify['permissions'],{'contents':'read'})
        self.assertEqual(report['permissions'],{'issues':'write'})
        self.assertNotIn('checkout',str(report))
        self.assertNotIn('self-hosted',str(doc))
        self.assertNotIn('continue-on-error',str(doc))
        self.assertNotIn('ADMIN',str(doc))
        self.assertEqual(verify['env']['ATLAS_VISUAL_CRAWL_CUSTOMER_ONLY'],'true')

    def test_scheduled_production_uses_viewer_readonly_contract(self):
        root=Path(__file__).resolve().parents[1]
        doc=yaml.load((root/'.github/workflows/atlas-runtime-qa-v3.yml').read_text(),Loader=yaml.BaseLoader)
        steps=doc['jobs']['runtime-qa']['steps']
        required=next(s for s in steps if s.get('name')=='Run required production certification')
        self.assertEqual(required['env']['ATLAS_VISUAL_CRAWL_CUSTOMER_ONLY'],'true')
        self.assertIn('--phase all',required['run'])
        supplementary=next(s for s in steps if s.get('id')=='supplementary_certification')
        self.assertIn("inputs.mode == 'targeted_preflight'",supplementary['if'])

    def test_worker_shutdown_is_not_automatically_oom(self):
        from scripts.classify_worker_shutdown import classify
        self.assertEqual(classify('The runner has received a shutdown signal.')['cause'],'SHUTDOWN_INITIATOR_UNPROVEN')
        self.assertEqual(classify('Out of memory: Killed process 123 (python3)')['cause'],'HOST_OOM_RECORDED')
        self.assertEqual(classify('operation canceled')['cause'],'INSUFFICIENT_EVIDENCE')

    def test_mobile_navigation_scopes_customer_grid_without_role_changes(self):
        from services.customer_navigation_contract import customer_mobile_navigation_css
        css=customer_mobile_navigation_css()
        self.assertIn('grid-template-columns:repeat(2,minmax(0,1fr))!important',css)
        self.assertIn('@media(max-width:420px)',css)
        app=(Path(__file__).resolve().parents[1]/'app.py').read_text()
        self.assertIn('if tuple(pages) == ("Home", "Research", "Watchlist", "Ask ATLAS"):',app)


class WarmDeploymentNavigation(unittest.TestCase):
    def test_actual_navigation_renders_when_old_contract_module_is_cached(self):
        import ast
        import sys
        import types
        from unittest.mock import patch
        root=Path(__file__).resolve().parents[1]
        source=ast.parse((root/'app.py').read_text())
        function=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='v784_top_nav')
        legacy=types.ModuleType('services.customer_navigation_contract')
        # A running pre-deployment interpreter has the original contract API,
        # but cannot import a newly added symbol from that cached module.
        legacy.CUSTOMER_ROUTES=('Home','Research','Watchlist','Ask ATLAS')
        self.assertFalse(hasattr(legacy,'customer_mobile_navigation_css'))
        class StreamlitStub:
            def __init__(self): self.session_state={}; self.styles=[]
            def markdown(self,value,**kwargs): self.styles.append(value)
            def radio(self,label,pages,**kwargs): return pages[kwargs['index']]
        st=StreamlitStub()
        namespace={'st':st}
        with patch.dict(sys.modules,{'services.customer_navigation_contract':legacy}):
            exec(compile(ast.Module(body=[function],type_ignores=[]),'app.py','exec'),namespace)
            self.assertEqual(namespace['v784_top_nav'](list(legacy.CUSTOMER_ROUTES)),'Home')
            self.assertTrue(any('grid-template-columns:repeat(2,minmax(0,1fr))' in s for s in st.styles))
            st.styles=[]
            self.assertEqual(namespace['v784_top_nav'](['Home','Report Card']),'Home')
            self.assertFalse(any('grid-template-columns' in s for s in st.styles))


class InitialShellSettling(unittest.TestCase):
    def execute(self, states, deadline=3):
        from scripts.wait_for_production_source import settle_initial_shell
        calls=[]; pauses=[]; clock=[0]
        async def probe():
            value=states[min(len(calls),len(states)-1)]; calls.append(value)
            if isinstance(value,Exception): raise value
            return value
        async def pause(seconds): pauses.append(seconds);clock[0]+=seconds
        result=asyncio.run(settle_initial_shell(probe,A,deadline=deadline,clock=lambda:clock[0],pause=pause))
        return result,calls,pauses

    def test_source_marker_can_precede_login_without_increasing_shared_bound(self):
        pending={'deployed_source_sha':A,'classification':'IN_PROGRESS'}
        ready={'deployed_source_sha':A,'classification':'PASS'}
        result,calls,pauses=self.execute([{'deployed_source_sha':'UNKNOWN','classification':'IN_PROGRESS'},pending,ready])
        self.assertEqual(result,ready);self.assertEqual(len(calls),3);self.assertEqual(pauses,[1,1])

    def test_wrong_sha_fatal_and_security_errors_never_settle_or_retry(self):
        for value in [
            {'deployed_source_sha':C,'classification':'IN_PROGRESS'},
            {'deployed_source_sha':A,'classification':'IN_PROGRESS','fatal_exception':True},
            {'deployed_source_sha':A,'classification':'DEPLOYMENT_DEFECT'},
            {'deployed_source_sha':'UNKNOWN','classification':'BROWSER_UNAVAILABLE'},
            {'deployed_source_sha':A,'classification':'IN_PROGRESS','sha_mismatch':True},
            {'deployed_source_sha':B,'classification':'DEPLOYMENT_NOT_READY'},
        ]:
            with self.subTest(value=value):
                result,calls,pauses=self.execute([value])
                self.assertEqual(result,value);self.assertEqual(len(calls),1);self.assertFalse(pauses)

    def test_expired_shell_still_fails_closed(self):
        pending={'deployed_source_sha':A,'classification':'IN_PROGRESS'}
        result,calls,pauses=self.execute([pending],deadline=2)
        self.assertEqual(pauses,[1,1]);self.assertEqual(len(calls),3)
        self.assertEqual(decision(result,A,B),'SOURCE_OR_APPLICATION_ERROR')

    def test_browser_exception_is_not_swallowed(self):
        with self.assertRaisesRegex(RuntimeError,'browser unavailable'):
            self.execute([RuntimeError('browser unavailable')])

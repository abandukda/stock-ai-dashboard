"""Workflow must invoke the real provider-free parser and fail closed on bad UTC."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
class CalendarWorkflowCLI(unittest.TestCase):
    def test_reviewed_workflow_command_executes_real_parser(self):
        d=yaml.load((ROOT/'.github/workflows/atlas_report_card_exchange_calendar.yml').read_text(),Loader=yaml.BaseLoader)
        job=d['jobs']['produce'];self.assertEqual(job['env']['PYTHONPATH'],'.');self.assertEqual(job['runs-on'],['self-hosted','Linux','X64','atlas-worker-1'])
        step=next(s for s in job['steps'] if s.get('name')=='Produce and replay-verify exact XNYS calendar')
        self.assertNotIn('${{',step['run'])
        with tempfile.TemporaryDirectory() as tmp:
            command=step['run'].replace('audit_results/report_card_calendar/xnys_calendar.json',tmp+'/calendar.json')
            env=dict(os.environ,PYTHONPATH=job['env']['PYTHONPATH'],CALENDAR_START_DATE='2026-10-02',CALENDAR_CUTOFF_UTC='2026-10-22T00:00:00Z')
            result=subprocess.run(['bash','-euo','pipefail','-c',command],cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            import json
            d=json.loads(Path(tmp+'/calendar.json').read_text())
            self.assertEqual(d['finalized_session'],'2026-10-21')
            self.assertIn('2026-10-12',d['trading_sessions'])
            self.assertNotIn('2026-10-10',d['trading_sessions'])
            self.assertEqual(d['version'],'4.13.2')
    def test_date_only_cutoff_fails_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'calendar.json'
            r=subprocess.run([sys.executable,'scripts/build_report_card_exchange_calendar.py','--start-date','2026-10-02','--cutoff-utc','2026-10-21','--output',str(path)],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(path.exists())

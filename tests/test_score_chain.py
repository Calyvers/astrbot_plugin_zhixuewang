"""Offline regression: run with python3 -m unittest discover -s tests."""
import ast
import asyncio
import importlib.util
import logging
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace as NS
ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
sf = load('zhixue_score_fallback')
rf = load('zhixue_rate_fallback')
def sheet(items):
    return {'sheet_datas': {'userAnswerRecordDTO': {'answerRecordDetails': items}}}
def question(n, score=8, full=10):
    return dict(dispTitle=str(n), score=score, standardScore=full)
def trend(pid='p'):
    return {'scoreLevelType':'score','list':[{'levelList':[
        dict(name=n,lowBound=float(lo),upperBound=float(hi)) for n,(lo,hi) in rf._VERIFIED_AXIS.items()],
        'dataList':[{'id':pid,'name':'exam','improveBar':{'show':True,'levelScale':'B等','offset':50}}]}]}
class Tests(unittest.TestCase):
    def test_sheet_complete(self):
        self.assertEqual(sf.extract_computed_score(sheet([question(1),question(2)]),20).score,16)
    def test_sheet_reject(self):
        for items,full in [([question(1)],20),([question(1),question(1)],20),
                           ([question(1,None)],10),([question(1,True)],10),
                           ([question(1,float('nan'))],10),([question(1,-1)],10),
                           ([question(1,11)],10),([question(1)],None)]:
            with self.subTest(items=items):
                self.assertIsNone(sf.extract_computed_score(sheet(items),full))
    def test_explicit_total(self):
        for value in [True, float('nan'),float('inf'),-1]:
            self.assertIsNone(sf.extract_total_score({'dispTitle':'总分','score':value}))
        self.assertIsNone(sf.extract_total_score({'score':5,'scoreSource':'teacher'}))
        self.assertEqual(sf.extract_total_score({'dispTitle':'总分','score':0}).score,0)
    def test_chain(self):
        # Execute actual get_marks AST without loading login/framework dependencies.
        tree=ast.parse((ROOT/'zhixue_core.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ZhiXueManager')
        method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='get_marks')
        env=dict(parse_trend=rf.parse_trend,get_fallback_score=sf.get_fallback_score,
                 logger=logging.getLogger('test'),__name__='offline')
        exec(compile(ast.Module(body=[method],type_ignores=[]),'get_marks','exec'),env)
        for report,raw,sheet_result,expected,source,expected_calls in [
            (0,trend(),None,0,'报告',[]),
            (None,trend(),None,78,'趋势区间插值',['trend']),
            (None,trend('wrong'),{'dispTitle':'总分','score':65},65,'答题卡',['trend','sheet']),
            (None,None,sheet([question(1,40,50),question(2,30,50)]),70,'答题卡计算',['trend','sheet']),
            (None,None,None,None,'报告',['trend','sheet']),
            (None,RuntimeError('offline'),None,None,'报告',['trend','sheet'])]:
            calls=[]
            paper=dict(subject_code='M',subject_name='Math',paper_id='p',score=report,standard_score=100)
            def get_trend(*args):
                calls.append('trend')
                if isinstance(raw,Exception): raise raw
                return raw
            def get_sheet(*args):
                calls.append('sheet');return sheet_result
            account=NS(name='test',get_report_main=lambda e:([paper],None),get_trend_result=get_trend,get_sheet_payload=get_sheet)
            async def get_account(*args): return account,None
            manager=NS(get_account=get_account,_resolve_exam_or_latest=lambda *a:NS(id='e',name='exam'))
            _,_,subjects,total=asyncio.run(env['get_marks'](manager,'u',[]))
            self.assertEqual(subjects[0]['score'],expected)
            self.assertEqual(subjects[0]['score_source'],source)
            self.assertEqual(calls,expected_calls)
            if source!='报告': self.assertIsNone(total['score'])
if __name__=='__main__': unittest.main()

"""Offline rank parser/core tests; no credentials or AstrBot runtime required."""
import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]

def load(filename, name, ns):
    tree = ast.parse((ROOT / filename).read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), ns)
    return ns[name]

class RankTests(unittest.TestCase):
    def test_values_and_args(self):
        ns = {}
        valid = load('zhixue_core.py', 'valid_rank', ns)
        for value in [None, True, False, 0, -1, 'nan', 'inf', 'bad', 2.5]:
            self.assertIsNone(valid(value))
        self.assertEqual(valid('13'), 13)
        parse = load('zhixue_core.py', 'parse_ranks_args', ns)
        for text, expected in [('', (None, False)), ('01', ('01', False)), ('all', (None, True)), ('all 01', ('01', True)), ('考试 名称', ('考试 名称', False))]:
            self.assertEqual(parse(text), expected)

    def test_core(self):
        ns = {}
        load('zhixue_core.py', 'valid_rank', ns)
        get = load('zhixue_core.py', 'get_ranks', ns)
        report = {'paperList': [{'paperId':'a','subjectName':'数学','clazzRank':13,'gradeRank':280}], 'absentPaperList':[{'paperId':'a'}, {'paperId':'b','subjectName':'历史','subjectLabels':[{'labelName':'未扫描'}]}]}
        account = SimpleNamespace(name='测试',get_rank_report=lambda exam:report)
        async def auth(*args): return account, None
        fake = SimpleNamespace(get_account=auth,_resolve_exam_or_latest=lambda *args:SimpleNamespace(id='1',name='考试'))
        result = asyncio.run(get(fake,'test',[]))
        self.assertEqual(len(result[2]),2)
        self.assertEqual(result[2][0]['grade_rank'],280)
        fmt = load('zhixue_core.py','format_ranks_table',{})
        text = fmt(result[0],result[1]['name'],result[2])
        self.assertIn('未扫描',text)
        self.assertIn('无排名',text)

    def test_api_errors(self):
        ns = {'Exam':object}
        get = load('zhixue_api.py','get_rank_report',ns)
        for body, ok in [({'errorCode':0,'result':{}},True),({'errorCode':1111},False),({'errorCode':0,'result':None},False)]:
            response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:body)
            fake=SimpleNamespace(_auth_token='dummy',_get_auth_header=lambda:{},_session=SimpleNamespace(get=lambda *a,**kw:response))
            if ok: self.assertEqual(get(fake,SimpleNamespace(id='1')), {})
            else:
                with self.assertRaises(RuntimeError):get(fake,SimpleNamespace(id='1'))

    def test_syntax(self):
        for path in ROOT.glob('*.py'): ast.parse(path.read_text())

if __name__ == '__main__': unittest.main()

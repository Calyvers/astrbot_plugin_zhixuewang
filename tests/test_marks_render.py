"""Exercise actual command body with framework/network dependencies stubbed."""
import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest

class MarksRenderTest(unittest.TestCase):
    def test_parameter_types(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ZhiXuePlugin')
        method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'zx_marks')
        method.decorator_list = []
        for param in (2, '02', '月考', None):
            for estimated in (False, True):
                with self.subTest(param=param, estimated=estimated):
                    rendered = []
                    async def marks(uid, users, value):
                        self.assertEqual(value, param)
                        return 'test', {'name': '实际考试'}, [{'score': 80, 'score_estimated': estimated}], None
                    async def render(template, data):
                        rendered.append(data)
                        return 'test-image'
                    def no_fallback(*args):
                        self.fail('Unexpected text fallback')
                    env = dict(AstrMessageEvent=object, zhixue_manager=SimpleNamespace(get_marks=marks),
                               MARKS_TMPL='', logger=logging.getLogger('test'), format_marks_table=no_fallback)
                    exec(compile(ast.Module(body=[method], type_ignores=[]), 'zx_marks', 'exec'), env)
                    plugin = SimpleNamespace(config={}, _render_image=render)
                    event = SimpleNamespace(get_sender_id=lambda: 'u', plain_result=lambda x: ('text', x),
                                            image_result=lambda x: ('image', x))
                    async def run():
                        return [x async for x in env['zx_marks'](plugin, event, param)]
                    result = asyncio.run(run())
                    self.assertEqual(result[-1], ('image', 'test-image'))
                    name = str(param) if param is not None else '实际考试'
                    self.assertEqual(rendered[0]['exam_name'], name + ('（含估算）' if estimated else ''))

if __name__ == '__main__':
    unittest.main()

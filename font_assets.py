"""System-only HTML fonts: tabular numbers, CJK text and symbol fallback."""

_FONT_STYLE = """<style id="zhixue-system-fonts">
/* Restrict the numeric face so Chinese text keeps its original font stack.
   Regular/bold faces are separate; no network font downloads are required. */
@font-face {
  font-family: 'Zhixue Numbers';
  src: local('DejaVu Sans Mono'), local('Consolas'), local('Liberation Mono'),
       local('Menlo'), local('Courier New');
  font-weight: 400;
  unicode-range: U+0020-0040, U+005B-0060, U+007B-007E, U+00B1,
                 U+00D7, U+00F7, U+2010-2015, U+2212;
}
@font-face {
  font-family: 'Zhixue Numbers';
  src: local('DejaVu Sans Mono Bold'), local('Consolas Bold'),
       local('Liberation Mono Bold'), local('Menlo Bold'), local('Courier New Bold');
  font-weight: 700;
  unicode-range: U+0020-0040, U+005B-0060, U+007B-007E, U+00B1,
                 U+00D7, U+00F7, U+2010-2015, U+2212;
}
body, table, th, td {
  font-family: 'Zhixue Numbers', 'Microsoft YaHei', 'Noto Sans CJK SC',
               'PingFang SC', 'Droid Sans Fallback', 'WenQuanYi Micro Hei',
               'DejaVu Sans', 'Noto Sans Math', 'Noto Sans Symbols 2',
               'Segoe UI Symbol', sans-serif !important;
  font-variant-numeric: lining-nums tabular-nums;
  font-variant-ligatures: none;
}
</style>"""


def embed_fonts(template: str) -> str:
    """Inject once into the existing HTML templates; preserve their content."""
    if 'id="zhixue-system-fonts"' in template:
        return template
    return template.replace("</head>", _FONT_STYLE + "</head>", 1)

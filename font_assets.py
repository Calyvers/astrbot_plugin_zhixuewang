"""Select system fallback fonts for HTML rendering; no fonts are bundled."""

def embed_fonts(template):
    css = "<style>body,table,th,td{font-family:'Microsoft YaHei','Noto Sans CJK SC',sans-serif !important;}</style>"
    return template.replace("</head>", css + "</head>", 1)

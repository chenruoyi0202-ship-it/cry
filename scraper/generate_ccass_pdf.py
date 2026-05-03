#!/usr/bin/env python3
"""
CCASS Markdown 报告 → PDF 转换

读取 data/stock_XXXXX_ccass_report.md，生成格式规范的 PDF 报告。
使用纯 Python（markdown + weasyprint），无需外部工具。

用法: python scraper/generate_ccass_pdf.py [stock_code]
"""

import os
import sys
import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'data')

CSS = """
@page {
    size: A4;
    margin: 20mm 15mm 20mm 15mm;
}
body {
    font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 11px;
    line-height: 1.7;
    color: #1a1a2e;
}
h1 {
    font-size: 18px;
    color: #CA8A04;
    border-bottom: 2px solid #CA8A04;
    padding-bottom: 6px;
    margin-bottom: 12px;
}
h2 {
    font-size: 14px;
    color: #1a1a2e;
    margin: 16px 0 8px;
    padding-left: 8px;
    border-left: 3px solid #CA8A04;
}
h3 {
    font-size: 12px;
    color: #333;
    margin: 12px 0 6px;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 12px;
    font-size: 10px;
}
th {
    background: #FEF3C7;
    color: #92400E;
    padding: 5px 6px;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid #CA8A04;
    white-space: nowrap;
}
td {
    padding: 4px 6px;
    border-bottom: 1px solid #E5E7EB;
    white-space: nowrap;
}
tr:nth-child(even) td {
    background: #F9FAFB;
}
strong {
    color: #1a1a2e;
}
ul, ol {
    padding-left: 18px;
    margin: 6px 0;
}
li {
    margin: 3px 0;
}
blockquote {
    border-left: 3px solid #D1D5DB;
    padding-left: 10px;
    color: #6B7280;
    margin: 10px 0;
    font-size: 10px;
}
hr {
    border: none;
    border-top: 1px solid #E5E7EB;
    margin: 14px 0;
}
code {
    background: #F3F4F6;
    padding: 1px 4px;
    border-radius: 2px;
    font-size: 10px;
    font-family: monospace;
}
.header-meta {
    text-align: right;
    font-size: 9px;
    color: #9CA3AF;
    margin-bottom: 8px;
}
.footer {
    text-align: center;
    font-size: 8px;
    color: #9CA3AF;
    margin-top: 20px;
    padding-top: 8px;
    border-top: 1px solid #E5E7EB;
}
"""


def md_to_pdf(md_path, pdf_path):
    """Convert markdown to styled PDF."""
    from weasyprint import HTML

    with open(md_path, encoding='utf-8') as f:
        md_content = f.read()

    # Convert markdown to HTML
    html_body = markdown.markdown(
        md_content,
        extensions=['tables', 'fenced_code'],
        output_format='html5'
    )

    # Wrap in full HTML document
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>{CSS}</style>
</head>
<body>
<div class="header-meta">
    02680 创陞控股 · CCASS 每日持股分析报告
</div>
{html_body}
<div class="footer">
    本报告由自动化脚本生成，不构成投资建议。数据来源：港交所 CCASS。
</div>
</body>
</html>"""

    HTML(string=html_doc).write_pdf(pdf_path)
    print(f'PDF 报告已生成: {pdf_path}')


def main():
    stock_code = sys.argv[1].zfill(5) if len(sys.argv) > 1 else '02680'
    md_path = os.path.join(DATA_DIR, f'stock_{stock_code}_ccass_report.md')
    pdf_path = os.path.join(DATA_DIR, f'stock_{stock_code}_ccass_report.pdf')

    if not os.path.exists(md_path):
        print(f'[error] 未找到报告: {md_path}', file=sys.stderr)
        sys.exit(1)

    md_to_pdf(md_path, pdf_path)


if __name__ == '__main__':
    main()

import sys
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

path = r"D:\FPTU\do_van_an\Documents\Reports\Report 4.0_TDS.docx"
doc = Document(path)
out = open(r"D:\FPTU\do_van_an\dailinh-odoo-erp\.tmp_tds\outline.txt", "w", encoding="utf-8")
def print(*a, **k):
    out.write(" ".join(str(x) for x in a) + "\n")

body = doc.element.body
idx = 0
for child in body.iterchildren():
    if child.tag == qn('w:p'):
        p = Paragraph(child, doc)
        txt = p.text.strip()
        style = p.style.name if p.style is not None else ''
        if txt:
            print(f"[{idx}] P <{style}> {txt[:160]}")
        idx += 1
    elif child.tag == qn('w:tbl'):
        t = Table(child, doc)
        nrows = len(t.rows)
        ncols = len(t.columns)
        try:
            hdr = " | ".join(c.text.strip()[:22] for c in t.rows[0].cells)
        except Exception:
            hdr = "?"
        print(f"[{idx}] TABLE {nrows}x{ncols} :: {hdr[:180]}")
        idx += 1

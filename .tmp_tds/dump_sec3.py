from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

path = r"D:\FPTU\do_van_an\Documents\Reports\Report 4.0_TDS.docx"
doc = Document(path)
out = open(r"D:\FPTU\do_van_an\dailinh-odoo-erp\.tmp_tds\sec3.txt", "w", encoding="utf-8")

START, END = 70, 213
idx = 0
for child in doc.element.body.iterchildren():
    if child.tag == qn('w:p'):
        if START <= idx < END:
            p = Paragraph(child, doc)
            style = p.style.name if p.style is not None else ''
            out.write(f"[{idx}] P <{style}> {p.text}\n")
        idx += 1
    elif child.tag == qn('w:tbl'):
        if START <= idx < END:
            t = Table(child, doc)
            out.write(f"[{idx}] TABLE {len(t.rows)}x{len(t.columns)}\n")
            for r in t.rows:
                cells = []
                seen = set()
                for c in r.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    cells.append(c.text.replace("\n", " / ").strip())
                out.write("      | " + " | ".join(cells) + "\n")
        idx += 1
    elif child.tag == qn('w:sectPr'):
        pass
    else:
        idx += 1
out.close()
print("ok")

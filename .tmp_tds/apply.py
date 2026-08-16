# -*- coding: utf-8 -*-
"""Replace section 3 (Data Model) of Report 4.0_TDS.docx with source-derived content."""
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document
from docx.oxml.ns import qn

import builder as B
from sec3_intro import (INTRO_LEAD, MECH_HEADERS, MECH_WIDTHS, MECH_ROWS,
                        COMMON_NOTE_LABEL, COMMON_NOTE, SUMMARY_INTRO,
                        SUM_HEADERS, SUM_WIDTHS, SUM_ROWS)
from sec3_ent1 import CH, CW, MODULE_A, MODULE_B, MODULE_C
from sec3_ent2 import MODULE_D
from sec3_ent3 import MODULE_E, MODULE_F, MODULE_G
from sec3_rest import (REL_LEAD, REL_HEADERS, REL_WIDTHS, REL_ROWS, REL_NOTE,
                       ENUM_LEAD, ENUM_HEADERS, ENUM_WIDTHS, ENUM_ROWS,
                       IDX_LEAD, IDX_HEADERS, IDX_WIDTHS, IDX_ROWS,
                       IDX_NOTE_LABEL, IDX_NOTE)

SRC = r"D:\FPTU\do_van_an\Documents\Reports\Report 4.0_TDS.docx"


def find_heading(doc, text):
    """Return the <w:p> element whose trimmed text equals `text`."""
    for p in doc.paragraphs:
        if p.text.strip() == text:
            return p._p
    raise SystemExit(f"!! Không tìm thấy heading: {text!r}")


def build_blocks():
    """Yield the new §3 content as a list of oxml elements."""
    out = []
    add = out.append

    add(B.para("3. Data Model", style="Heading1"))
    add(B.para(INTRO_LEAD))
    add(B.para(""))
    add(B.para("Cơ chế kế thừa Odoo áp dụng trong dự án:", bold=True, sz=26))
    add(B.table(MECH_HEADERS, MECH_ROWS, MECH_WIDTHS))
    add(B.para(""))
    add(B.note_box(COMMON_NOTE_LABEL, COMMON_NOTE))
    add(B.para(""))
    add(B.para(SUMMARY_INTRO, bold=True, sz=26))
    add(B.table(SUM_HEADERS, SUM_ROWS, SUM_WIDTHS))
    add(B.para(""))

    # ── 3.1 ──
    add(B.para("3.1 Entity Definitions", style="Heading2"))
    for mod in (MODULE_A, MODULE_B, MODULE_C, MODULE_D, MODULE_E, MODULE_F, MODULE_G):
        add(B.para(mod["title"], style="Heading3"))
        add(B.para(mod["lead"]))
        for ent in mod["entities"]:
            add(B.para(ent["head"], style="Heading4"))
            add(B.para(ent["desc"]))
            if ent.get("meta"):
                add(B.para(ent["meta"], italic=True, sz=20, color="555555"))
            if ent.get("note"):
                add(B.note_box(ent["note"][0], ent["note"][1]))
            if ent.get("cols"):
                add(B.table(CH, ent["cols"], CW))
            if ent.get("extra"):
                add(B.para(ent["extra"], sz=20, color="555555"))
            add(B.para(""))

    # ── 3.2 ──
    add(B.para("3.2 Entity Relationships", style="Heading2"))
    add(B.para(REL_LEAD))
    add(B.table(REL_HEADERS, REL_ROWS, REL_WIDTHS))
    add(B.para(""))
    add(B.note_box("Tham chiếu mềm (không có FOREIGN KEY)", REL_NOTE))
    add(B.para(""))

    # ── 3.3 ──
    add(B.para("3.3 Enum / Lookup Values", style="Heading2"))
    add(B.para(ENUM_LEAD))
    add(B.table(ENUM_HEADERS, ENUM_ROWS, ENUM_WIDTHS))
    add(B.para(""))

    # ── 3.4 ──
    add(B.para("3.4 Indexing Strategy", style="Heading2"))
    add(B.para(IDX_LEAD))
    add(B.table(IDX_HEADERS, IDX_ROWS, IDX_WIDTHS))
    add(B.para(""))
    add(B.note_box(IDX_NOTE_LABEL, IDX_NOTE))
    add(B.para(""))
    return out


def main():
    if not os.path.exists(SRC):
        raise SystemExit(f"!! Không thấy file: {SRC}")
    lock = os.path.join(os.path.dirname(SRC), "~$" + os.path.basename(SRC))
    if os.path.exists(lock):
        raise SystemExit("!! File đang mở trong Word (còn file khoá ~$). Đóng Word rồi chạy lại.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = SRC.replace(".docx", f".backup-{stamp}.docx")
    shutil.copy2(SRC, backup)
    print(f"[backup] {backup}")

    doc = Document(SRC)
    start = find_heading(doc, "3. Data Model")
    end = find_heading(doc, "4. Security Design")

    # collect everything strictly between start (inclusive) and end (exclusive)
    body = start.getparent()
    children = list(body)
    i0, i1 = children.index(start), children.index(end)
    doomed = children[i0:i1]
    print(f"[remove] {len(doomed)} block(s) từ '3. Data Model' đến trước '4. Security Design'")

    blocks = build_blocks()
    print(f"[insert] {len(blocks)} block(s) mới")

    for el in blocks:
        end.addprevious(el)
    for el in doomed:
        body.remove(el)

    doc.save(SRC)
    print(f"[saved]  {SRC}")


if __name__ == "__main__":
    main()

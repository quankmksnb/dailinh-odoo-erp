# -*- coding: utf-8 -*-
"""Kiểm tra file .drawio: XML hợp lệ, id không trùng, edge có đủ hai đầu."""
import os
import xml.etree.ElementTree as ET
from collections import Counter

p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "docs", "DLM-ERP_Conceptual_ERD.drawio")
root = ET.parse(p).getroot()
ok = True
seen = {}          # (src,tgt) -> tên trang  : quan hệ chỉ được vẽ 1 lần ở sub-ERD
full = {}          # entity     -> tên trang  : attribute chỉ hiện đầy đủ 1 lần
for d in root.findall("diagram"):
    cells = d.findall(".//mxCell")
    ids = [c.get("id") for c in cells]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    verts = {c.get("id") for c in cells if c.get("vertex") == "1"}
    edges = [c for c in cells if c.get("edge") == "1"]
    missing = [(e.get("source"), e.get("target")) for e in edges
               if e.get("source") not in verts or e.get("target") not in verts]
    print("[%s] cells=%d vertex=%d edge=%d" % (d.get("name"), len(cells),
                                               len(verts), len(edges)))
    if dup:
        ok = False
        print("   !! id trùng:", dup)
    if missing:
        ok = False
        print("   !! edge thiếu đầu nối:", missing)
    if d.get("name", "").startswith("0."):
        continue                      # sơ đồ tổng thể là superset, bỏ qua
    for e in edges:
        # một cặp entity có thể có nhiều quan hệ khác nhau (VD: ISA và produces)
        # nên khóa gồm cả nhãn quan hệ
        k = tuple(sorted((e.get("source"), e.get("target")))) + (e.get("value"),)
        if k in seen:
            ok = False
            print("   !! quan hệ trùng với [%s]: %s" % (seen[k], k))
        seen[k] = d.get("name")
    for c in cells:
        if c.get("vertex") == "1" and "swimlane" in (c.get("style") or ""):
            k = c.get("id")
            if k in full:
                ok = False
                print("   !! entity vẽ đầy đủ 2 lần (%s / %s): %s"
                      % (full[k], d.get("name"), k))
            full[k] = d.get("name")
print("OK" if ok else "CO LOI")

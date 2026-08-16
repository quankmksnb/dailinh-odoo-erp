"""Extract Odoo model definitions from source (AST-based, no guessing)."""
import ast
import os
import sys

ROOT = r"D:\FPTU\do_van_an\dailinh-odoo-erp\dlm-erp"
OUT = open(r"D:\FPTU\do_van_an\dailinh-odoo-erp\.tmp_tds\models_survey.txt", "w", encoding="utf-8")


def w(s=""):
    OUT.write(s + "\n")


def lit(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def src(node):
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


FIELD_TYPES = {
    "Char", "Text", "Html", "Boolean", "Integer", "Float", "Monetary", "Date",
    "Datetime", "Binary", "Image", "Selection", "Many2one", "One2many",
    "Many2many", "Reference", "Json", "Properties",
}


def describe_field(call):
    ftype = call.func.attr if isinstance(call.func, ast.Attribute) else src(call.func)
    pos = [src(a) for a in call.args]
    kw = {k.arg: k.value for k in call.keywords if k.arg}
    parts = []
    if ftype in ("Many2one", "One2many", "Many2many"):
        parts.append("->" + (pos[0] if pos else src(kw.get("comodel_name", ast.Constant("?")))))
        if ftype == "One2many" and len(pos) > 1:
            parts.append("inv=" + pos[1])
        if ftype == "Many2many":
            for k in ("relation", "column1", "column2"):
                if k in kw:
                    parts.append(f"{k}={src(kw[k])}")
    for k in ("string", "required", "readonly", "store", "compute", "related",
              "default", "ondelete", "index", "tracking", "copy", "digits",
              "domain", "group_operator", "inverse", "auto_join", "size"):
        if k in kw:
            v = src(kw[k])
            if len(v) > 90:
                v = v[:87] + "..."
            parts.append(f"{k}={v}")
    sel = None
    if ftype == "Selection":
        selnode = kw.get("selection") or (call.args[0] if call.args else None)
        if selnode is not None:
            val = lit(selnode)
            if isinstance(val, list):
                sel = [x[0] for x in val if isinstance(x, (list, tuple))]
            else:
                sel = "DYNAMIC:" + src(selnode)[:70]
        if "selection_add" in kw:
            val = lit(kw["selection_add"])
            sel = "ADD:" + str(val)
    return ftype, " ".join(parts), sel


def walk_module(mod_dir, mod_name):
    py_files = []
    for sub in ("models", "wizard", "wizards", "controllers", "report", "reports"):
        d = os.path.join(mod_dir, sub)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".py") and f != "__init__.py":
                    py_files.append(os.path.join(d, f))
    for f in sorted(os.listdir(mod_dir)):
        if f.endswith(".py") and f != "__init__.py":
            py_files.append(os.path.join(mod_dir, f))

    for path in py_files:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            w(f"  !! parse error {path}: {e}")
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = {}
            fields = []
            methods = []
            sqls = []
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                    tname = stmt.targets[0].id
                    if tname.startswith("_"):
                        if tname == "_sql_constraints":
                            val = lit(stmt.value)
                            if val:
                                sqls = val
                        else:
                            attrs[tname] = lit(stmt.value) if lit(stmt.value) is not None else src(stmt.value)
                    elif isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Attribute) \
                            and stmt.value.func.attr in FIELD_TYPES:
                        fields.append((tname, describe_field(stmt.value)))
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    pass
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    decs = []
                    for d in stmt.decorator_list:
                        decs.append(src(d))
                    cons = [d for d in decs if "constrains" in d]
                    if cons:
                        methods.append(("CONSTRAINS", stmt.name, cons))

            if not attrs.get("_name") and not attrs.get("_inherit") and not attrs.get("_inherits"):
                continue
            w("")
            w(f"### CLASS {node.name}   [{rel}]")
            for k in ("_name", "_inherit", "_inherits", "_description", "_order",
                      "_rec_name", "_table", "_auto", "_parent_name", "_parent_store", "_log_access"):
                if k in attrs:
                    w(f"    {k} = {attrs[k]!r}")
            if sqls:
                for s in sqls:
                    w(f"    SQL_CONSTRAINT {s}")
            for fname, (ftype, meta, sel) in fields:
                line = f"    {fname}: {ftype} {meta}"
                w(line.rstrip())
                if sel:
                    w(f"        SELECTION {sel}")
            for kind, mname, decs in methods:
                w(f"    {kind} {mname} {decs}")


mods = sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)) and d.startswith("dl_"))
for m in mods:
    md = os.path.join(ROOT, m)
    manifest = os.path.join(md, "__manifest__.py")
    w("")
    w("=" * 100)
    w(f"MODULE {m}")
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as fh:
            man = ast.literal_eval(ast.parse(fh.read()).body[0].value)
        w(f"  version={man.get('version')}  depends={man.get('depends')}")
    w("=" * 100)
    walk_module(md, m)

OUT.close()
print("done")

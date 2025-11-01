# -*- coding: utf-8 -*-
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
from pathlib import Path
import json, os, re, tempfile
from final import generate_report as generate_report_full  # 原始3语言函数

app = Flask(__name__)

# ---------- 包装器：让 generate_report 兼容 2 文件 ----------
def generate_report(path_a, path_b):
    """
    Wrapper for generate_report(en_path, de_path, lv_path)
    自动生成一个假的 LV 文件（空段落），以便旧版本兼容。
    """
    dummy_lv = Path(tempfile.gettempdir()) / "dummy_lv.json"
    with open(path_a, encoding="utf-8") as f:
        data_a = json.load(f)

    # 创建空结构（和 EN 一样长度）
    if isinstance(data_a, list) and "para" in data_a[0]:
        count = len(data_a[0]["para"])
    else:
        count = len(data_a)

    dummy_data = [{
        "para": [{"para_number": i + 1, "para": ""} for i in range(count)]
    }]
    with open(dummy_lv, "w", encoding="utf-8") as f:
        json.dump(dummy_data, f, ensure_ascii=False)

    return generate_report_full(path_a, path_b, dummy_lv)


# ---------- 实体高亮 ----------
@app.template_filter("highlight_entities")
def highlight_entities(text, entities):
    if not text or not entities:
        return text

    highlighted = text
    all_values = []

    if isinstance(entities, dict):
        for k, vals in entities.items():
            if isinstance(vals, list):
                all_values.extend(vals)
            elif vals:
                all_values.append(str(vals))

    for val in sorted(set(all_values), key=len, reverse=True):
        if not val or len(val) < 2:
            continue
        pattern = re.escape(val)
        highlighted = re.sub(
            pattern,
            f'<span class="entity-highlight">{val}</span>',
            highlighted,
            flags=re.IGNORECASE
        )
    return highlighted


# ---------- 首页 ----------
@app.route('/')
def index():
    return render_template('upload.html')


# ---------- 文件比较 ----------
@app.route('/compare', methods=['POST'])
def compare_files():
    file_a = request.files.get('fileA')
    file_b = request.files.get('fileB')

    if not file_a or not file_b:
        return "Please upload two files.", 400

    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)

    path_a = upload_dir / secure_filename(file_a.filename)
    path_b = upload_dir / secure_filename(file_b.filename)
    file_a.save(path_a)
    file_b.save(path_b)

    rows = generate_report(path_a, path_b)  # ✅ 调用包装后的函数

    # 保存结果
    result_dir = Path("results")
    result_dir.mkdir(exist_ok=True)
    with open(result_dir / "comparison.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    return render_template("report.html", rows=rows,
                           fileA=file_a.filename, fileB=file_b.filename)


# ---------- 启动 Flask ----------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

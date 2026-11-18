"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    line_errors = defaultdict(lambda: defaultdict(set))
    remove_images = set()
    missing_labels = set()
    rename_classes = any(
        issue.severity == ERROR and issue.code == "BAD_CLASS_NAME"
        for issue in issues
    )
    removable_line_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    removable_image_codes = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}

    for issue in issues:
        if issue.severity != ERROR:
            continue
        if issue.code.startswith("DUP_IMAGE_") or issue.code in removable_image_codes:
            if issue.image not in ("data.yaml", "<dataset>"):
                remove_images.add(issue.image)
        elif issue.code == "MISSING_LABEL_FILE":
            missing_labels.add(issue.image)
        elif issue.line is not None and issue.code in removable_line_codes | {"BOX_OUT_OF_IMAGE"}:
            line_errors[issue.image][issue.line].add(issue.code)

    fixes = []
    for stem in sorted(remove_images):
        image_path = ds.image_path(stem)
        if image_path is None:
            continue
        label_path = ds.label_path(stem)
        image_path.unlink()
        label_path.unlink(missing_ok=True)
        fixes.append({
            "image": stem, "line": "", "action": "remove_image",
            "before": image_path.name, "after": "đã xoá ảnh và nhãn",
        })

    for stem in sorted(missing_labels - remove_images):
        if ds.image_path(stem) is not None and not ds.label_path(stem).exists():
            fixes.append({
                "image": stem, "line": "", "action": "needs_label",
                "before": "(không có file)", "after": "chuyển người gán",
            })

    for stem in sorted(line_errors):
        if stem in remove_images or ds.image_path(stem) is None:
            continue
        label_path = ds.label_path(stem)
        if not label_path.exists():
            continue
        original_lines = label_path.read_text(encoding="utf-8", errors="replace").splitlines()
        changed_lines = list(original_lines)
        for line_no, codes in sorted(line_errors[stem].items()):
            if not 1 <= line_no <= len(original_lines):
                continue
            before = original_lines[line_no - 1]
            if codes & removable_line_codes:
                changed_lines[line_no - 1] = None
                fixes.append({
                    "image": stem, "line": line_no, "action": "drop_line",
                    "before": before, "after": "",
                })
                continue
            if "BOX_OUT_OF_IMAGE" not in codes:
                continue
            try:
                cls, cx, cy, width, height = parse_yolo_line(before)
            except (ValueError, OverflowError):
                continue
            x1, y1 = max(0.0, cx - width / 2), max(0.0, cy - height / 2)
            x2, y2 = min(1.0, cx + width / 2), min(1.0, cy + height / 2)
            if x2 <= x1 or y2 <= y1:
                changed_lines[line_no - 1] = None
                fixes.append({
                    "image": stem, "line": line_no, "action": "drop_line",
                    "before": before, "after": "",
                })
                continue
            clipped = (cls, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)
            after = f"{clipped[0]} " + " ".join(f"{value:.12g}" for value in clipped[1:])
            changed_lines[line_no - 1] = after
            fixes.append({
                "image": stem, "line": line_no, "action": "clip_box",
                "before": before, "after": after,
            })
        if changed_lines != original_lines:
            label_path.write_text("\n".join(line for line in changed_lines if line is not None) + ("\n" if changed_lines else ""), encoding="utf-8")

    if rename_classes:
        before = ds.yaml_path.read_text(encoding="utf-8") if ds.yaml_path.exists() else ""
        data = yaml.safe_load(before) or {}
        data["names"] = {index: name for index, name in enumerate(cfg["classes"])}
        after = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        ds.yaml_path.write_text(after, encoding="utf-8")
        fixes.append({
            "image": "data.yaml", "line": "", "action": "rename_classes",
            "before": before, "after": after,
        })
    return fixes

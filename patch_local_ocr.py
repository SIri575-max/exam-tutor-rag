"""Reversible, recorded guard for MinerU 4.0.12 zero-pixel OCR crop boxes.

Upstream callers already discard None crops. Preserve all valid crop paths unchanged.
"""
import datetime as dt
import json
from pathlib import Path
from sync_sources import ROOT, fingerprint

TARGET = ROOT / '.venv-ocr/Lib/site-packages/mineru/model/ocr/image.py'
BEFORE = '''    return rotate_vertical_crop_if_needed(get_rotate_crop_image(img, points))'''
AFTER = '''    # Local compatibility guard: detections with no pixel extent have no readable content.
    crop_width = int(max(np.linalg.norm(points[0] - points[1]), np.linalg.norm(points[2] - points[3])))
    crop_height = int(max(np.linalg.norm(points[0] - points[3]), np.linalg.norm(points[1] - points[2])))
    if min(crop_width, crop_height) < 1:
        import warnings
        warnings.warn("Skipped zero-pixel OCR crop; original page retained", RuntimeWarning, stacklevel=2)
        return None
    return rotate_vertical_crop_if_needed(get_rotate_crop_image(img, points))'''


def apply():
    base = ROOT / 'data/private/full-book/environment-patches'
    base.mkdir(parents=True, exist_ok=True)
    source = TARGET.read_text(encoding='utf-8')
    if AFTER in source:
        return 'already_applied'
    if source.count(BEFORE) != 1:
        raise ValueError('Installed OCR source differs; inspect before applying this guard')
    backup = base / 'ocr-image-before.py'
    if backup.exists():
        raise ValueError('Original backup already exists; inspect patch state')
    backup.write_bytes(TARGET.read_bytes())
    before_sha = fingerprint(TARGET)
    TARGET.write_text(source.replace(BEFORE, AFTER), encoding='utf-8')
    record = {'id': 'mineru-4.0.12-zero-pixel-crop-guard-v1', 'applied_at': dt.datetime.now().astimezone().isoformat(),
              'target': str(TARGET), 'original_backup': str(backup), 'before_sha256': before_sha,
              'after_sha256': fingerprint(TARGET), 'trigger_pdf_page': 129,
              'reason': 'A subpixel OCR detection rounds to zero width/height; docvortex correctly rejects zero-sized warp.',
              'behavior': 'Return None for zero-pixel crops; existing caller skips them. All nonzero crop paths unchanged.',
              'validation': 'synthetic valid/zero-width/zero-height crops checked locally; failed page must be reparsed separately'}
    (base / 'manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


if __name__ == '__main__':
    print(json.dumps(apply(), ensure_ascii=False, indent=2))

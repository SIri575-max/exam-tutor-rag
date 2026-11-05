"""Private, local-only image queries. Uploaded data never enters source indexes."""
import concurrent.futures
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/private/photo-queries'
MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_TEXT = 16000
ENGINE = ROOT / '.venv-ocr/Scripts/mineru-kit.exe'
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='photo-ocr')
_slots = threading.BoundedSemaphore(3)  # One running, at most two waiting.
_lock = threading.RLock()
_active = set()


class BusyError(ValueError):
    pass


def _folder(job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise ValueError('无效识别任务编号')
    return BASE / job_id


def _save(folder, data):
    with _lock:
        target = folder / 'status.json'
        tmp = folder / 'status.tmp'
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(target)


def preprocessing(crop=None, rotation=0):
    if type(rotation) is not int or rotation not in {0,90,180,270}:
        raise ValueError('旋转角度只支持0、90、180、270度')
    if crop is not None:
        if not isinstance(crop,list) or len(crop)!=4 or any(type(v) not in {int,float} or not math.isfinite(v) for v in crop):
            raise ValueError('裁剪区域应为四个0到1之间的坐标')
        x0,y0,x1,y1=crop
        if not (0<=x0<x1<=1 and 0<=y0<y1<=1):
            raise ValueError('裁剪区域超出图片或未包含有效范围')
        crop=list(crop)
    return {'crop':crop,'rotation_clockwise':rotation,'coordinate_space':'after_exif_then_rotation'}


def normalize_image(raw, crop=None, rotation=0, border=50):
    options=preprocessing(crop,rotation)
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('请选择不超过12MB的单张题图')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in {'PNG', 'JPEG', 'WEBP'} or getattr(im, 'n_frames', 1) != 1:
                raise ValueError('支持单张PNG、JPEG、WebP图片，请先转换其他格式')
            if im.width * im.height > MAX_PIXELS or min(im.size) < 40:
                raise ValueError('图片尺寸需至少40像素，且总像素不超过2000万')
            im = ImageOps.exif_transpose(im)
            if rotation:
                im=im.rotate(-rotation,expand=True)
            if options['crop'] is not None:
                x0,y0,x1,y1=options['crop'];w,h=im.size
                rectangle=(math.floor(x0*w),math.floor(y0*h),math.ceil(x1*w),math.ceil(y1*h))
                if min(rectangle[2]-rectangle[0],rectangle[3]-rectangle[1])<40:
                    raise ValueError('选框太小，请保留完整题干和公式（宽高至少40像素）')
                im=im.crop(rectangle)
            rgba = im.convert('RGBA')
            image = Image.new('RGB', rgba.size, 'white')
            image.paste(rgba, mask=rgba.getchannel('A'))
            image.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
            image = ImageOps.expand(image, border=border, fill='white')
            output = io.BytesIO()
            image.save(output, format='PNG')  # No original EXIF/GPS in the displayed image.
            return output.getvalue(), image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('图片无法读取，请重新拍摄或另存为PNG/JPEG') from exc


def _text(value, kind=''):
    """Preserve typed math, never infer a source page or execute image instructions."""
    if isinstance(value, list):
        return ''.join(_text(v) for v in value)
    if isinstance(value, dict):
        return _text(value.get('content', value.get('text', value.get('latex', ''))), value.get('type', ''))
    if not isinstance(value, str):
        return ''
    if kind.startswith('equation'):
        delimiter = '$' if kind == 'equation_inline' else '$$'
        return delimiter + value.strip() + delimiter
    return value


def review_warnings(text):
    warnings=[]
    if '\ufffd' in text:
        warnings.append('出现无法识别的字符，请对照原图补全。')
    formulas=re.findall(r'\$\$([\s\S]+?)\$\$|(?<!\$)\$([^$\n]+?)\$(?!\$)',text)
    for pair in formulas:
        formula=pair[0] or pair[1]
        without_text=re.sub(r'\\text(?:normal|rm|sf|tt)?\s*\{[^{}]*\}','',formula)
        if re.search(r'[\u4e00-\u9fff]',without_text):
            warnings.append('公式段中混入中文，可能误识别了手写批注，请逐字核对。')
            break
    return warnings


def transcript(parsed):
    if parsed.get('schema') != 'docvortex.middle' or str(parsed.get('schema_version')) != '2.0':
        raise ValueError('识别输出格式不匹配')
    blocks = []
    total = 0
    for page in parsed.get('pages', []):
        for block in page.get('blocks', []):
            if block.get('type') in {'header', 'footer', 'page_number', 'image'}:
                continue
            text = _text(block.get('content'), block.get('type', '')).strip()
            if not text:
                continue
            total += len(text)
            if total > MAX_TEXT or len(blocks) >= 80:
                raise ValueError('识别内容过长，请裁剪到一道题后重试')
            blocks.append({'id': len(blocks), 'type': block.get('type', 'text'),
                           'text': text, 'bbox': block.get('bbox'),'warnings':review_warnings(text)})
    if not blocks:
        raise ValueError('未识别到题干或公式，请拍清单题、避免反光后重试')
    return {'blocks': blocks, 'text': '\n\n'.join(b['text'] for b in blocks),
            'review_status': 'pending_user_review', 'source_channel': 'uploaded_query',
            'boundary': '原始识别稿，公式、数字、下标及所求量均需对照原图核对；不写入教材题库。'}


def _run_engine(folder):
    env = os.environ.copy()
    env.update({'MINERU_HOME': str(ROOT / 'data/private/ocr-pilot/mineru-home'),
                'HF_HOME': str(ROOT / 'data/private/ocr-pilot/model-cache/huggingface'),
                'MODELSCOPE_CACHE': str(ROOT / 'data/private/ocr-pilot/model-cache/modelscope'),
                'HF_HUB_DISABLE_XET': '1', 'HF_HUB_OFFLINE': '1',
                'MINERU_INTRA_OP_NUM_THREADS': '2', 'MINERU_INTER_OP_NUM_THREADS': '1',
                'MINERU_MODEL_SMALL_BACKEND': 'onnx'})
    command = [str(ENGINE), 'parse', str(folder / 'input.png'), '-o', str(folder / 'ocr'),
               '--format', 'middle_json', '--tier', 'basic', '--ocr-mode', 'ocr',
               '--disable-image-analysis']
    with (folder / 'engine.log').open('wb') as log:
        subprocess.run(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                       timeout=300, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return json.loads((folder / 'ocr/input.json').read_text(encoding='utf-8'))


def _work(job_id):
    folder = _folder(job_id)
    started = time.monotonic()
    data = {'job_id': job_id}
    try:
        with _lock:
            data = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
            data.update(status='running', message='本机正在识别文字与公式，通常需要几十秒；识别后请核对。')
            _save(folder, data)
        parsed = _run_engine(folder)
        result = transcript(parsed)
        # Keep raw output immutable; transcription is derived and explicitly unreviewed.
        result['raw_ocr_sha256'] = hashlib.sha256((folder / 'ocr/input.json').read_bytes()).hexdigest()
        data.update(status='ready', message='识别完成，请选取题干并核对公式。', result=result)
    except subprocess.TimeoutExpired:
        data.update(status='failed', message='识别超过5分钟，请裁剪单题后重试。')
    except (ValueError, FileNotFoundError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else '本机OCR组件或识别输出缺失，请检查本地安装。'
        data.update(status='failed', message=message)
    except Exception:
        # Do not return subprocess commands, local paths, environment or log content.
        data.update(status='failed', message='本机OCR未完成，请裁剪清晰单题后重试；也可直接输入题干。')
    finally:
        data['elapsed_seconds'] = round(time.monotonic() - started, 2)
        with _lock:
            _save(folder, data)
            _active.discard(job_id)
        _slots.release()


def submit(raw, crop=None, rotation=0, parent_job_id=None):
    if not ENGINE.is_file():
        raise ValueError('本机公式OCR尚未安装，请先配置独立OCR环境')
    options=preprocessing(crop,rotation)
    normalized, dimensions = normalize_image(raw,crop,rotation)
    if not _slots.acquire(blocking=False):
        raise BusyError('已有3个识别任务，请等待完成后再上传')
    job_id = uuid.uuid4().hex
    folder = _folder(job_id)
    try:
        folder.mkdir(parents=True)
        (folder / 'original.bin').write_bytes(raw)
        (folder / 'input.png').write_bytes(normalized)
        # A full, EXIF-oriented preview supports recropping without losing the original.
        full,_=normalize_image(raw,border=0)
        (folder/'full.png').write_bytes(full)
        data = {'job_id': job_id, 'status': 'queued', 'message': '已加入本机识别队列。',
                'engine': 'MinerU 4.0.12 / basic / ONNX CPU', 'local_only': True,
                'image_sha256': hashlib.sha256(raw).hexdigest(), 'dimensions': dimensions,
                'image_url': f'/api/photo-image?id={job_id}',
                'full_image_url': f'/api/photo-image?id={job_id}&view=full',
                'preprocessing':options,'parent_job_id':parent_job_id,
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        with _lock:
            _save(folder, data)
            _active.add(job_id)
        _pool.submit(_work, job_id)
        return data.copy()
    except Exception:
        with _lock:
            _active.discard(job_id)
        _slots.release()
        raise


def get(job_id):
    folder = _folder(job_id)
    with _lock:
        data = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
        if data['status'] in {'queued', 'running'} and job_id not in _active:
            data.update(status='failed', message='服务已重启，原任务中断，请重新上传。')
            _save(folder, data)
    if data.get('status')=='ready':
        for block in data['result']['blocks']:
            block.setdefault('warnings',review_warnings(block['text']))
    return data


def image_bytes(job_id, view='input'):
    if view not in {'input','full'}:
        raise ValueError('无效图片视图')
    folder=_folder(job_id)
    if view=='full' and not (folder/'full.png').exists():
        # Older jobs predate crop support. Derive an unpadded preview from their original.
        with _lock:
            full,_=normalize_image((folder/'original.bin').read_bytes(),border=0)
            (folder/'full.png').write_bytes(full)
    target=folder/'full.png' if view=='full' else folder/'input.png'
    return target.read_bytes()


def resubmit(job_id,crop=None,rotation=0):
    # Always crop the original, never a prior cropped/resized OCR input.
    try:raw=(_folder(job_id)/'original.bin').read_bytes()
    except FileNotFoundError as exc:raise ValueError('原始题图不存在，请重新上传。') from exc
    return submit(raw,crop,rotation,parent_job_id=job_id)

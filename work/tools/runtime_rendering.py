"""Bounded, language-independent blank-description checks; not OCR or text fidelity.

The fixed crop excludes window borders and selected-item icons. It expects the
native bag's grey background plus black/white glyph pixels. Absence is a blank
regression only when the Chinese reference contains that signal. Pixel presence
cannot establish legibility, correct wording, clipping or the identity of text.
"""
import hashlib
import io
import stat
from collections import Counter
from pathlib import Path

from PIL import Image

PROFILE = 'bag_description_v1'
SIZE = (256, 384)
CROP = (16, 145, 240, 192)
MAX_BYTES = 2 * 1024 * 1024
BUILD_ROOT = Path(__file__).resolve().parents[1] / 'build'


def validate_expectations(config):
    if not isinstance(config, dict):
        raise ValueError('rendering expectations must be an object')
    for name, spec in config.items():
        if not isinstance(name, str) or not name or not isinstance(spec, dict):
            raise ValueError('invalid rendering checkpoint')
        if set(spec) != {'profile', 'since', 'item', 'heap'}:
            raise ValueError('rendering configuration keys differ')
        if spec['profile'] != PROFILE or not isinstance(spec['since'], str) or not spec['since'] or spec['since'] == name:
            raise ValueError('invalid rendering profile or baseline')
        if type(spec['item']) is not int or not 1 <= spec['item'] <= 65535 or type(spec['heap']) is not int or not 0 <= spec['heap'] <= 255:
            raise ValueError('invalid expected item/heap')


def analyze_png(path):
    """Read at most MAX_BYTES+1 and reject unexpected image layouts before load."""
    result = {'status': 'incomplete'}
    try:
        if not isinstance(path, str) or not path:
            raise ValueError('missing screenshot path')
        if not stat.S_ISREG(Path(path).stat().st_mode):
            raise ValueError('screenshot is not a regular file')
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('screenshot exceeds byte limit')
        result.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        with Image.open(io.BytesIO(data)) as source:
            if source.format != 'PNG' or source.size != SIZE or getattr(source, 'n_frames', 1) != 1:
                raise ValueError('expected single-frame 256x384 PNG')
            source.load()
            rgba = source.convert('RGBA')
            if rgba.getextrema()[3] != (255, 255):
                raise ValueError('non-opaque screenshot')
            crop = rgba.convert('RGB').crop(CROP)
            counts = Counter(crop.get_flattened_data() if hasattr(crop, 'get_flattened_data') else crop.getdata())
        area = (CROP[2] - CROP[0]) * (CROP[3] - CROP[1])
        background = counts[(144, 144, 152)]
        black = counts[(0, 0, 0)]
        white = counts[(248, 248, 248)]
        result.update(size=list(SIZE), crop=list(CROP), pixels=area,
                      background=background, black=black, white=white)
        # Solid crop is unequivocally blank. Other absent signals are unknown,
        # not presumed blank (wrong screens, corrupt palettes, transitions).
        if background == area:
            result['status'] = 'blank'
        elif background >= area // 2 and black >= 16 and white >= 16:
            result['status'] = 'present'
        else:
            result['error'] = 'unrecognized description pixels'
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        result['error'] = str(exc)
    return result


def _checkpoint(run, name, spec):
    try:
        checkpoints = run['raw']['checkpoints']
        point, baseline = checkpoints[name], checkpoints[spec['since']]
        frame, since = point['frame'], baseline['frame']
        if type(frame) is not int or type(since) is not int or not 0 <= since < frame:
            raise ValueError('invalid checkpoint frames')
        requests = point['item_description_reads']
        if not isinstance(requests, list) or not requests:
            raise ValueError('missing item context')
        prior = -1
        for request in requests:
            observed = request['frame']
            if type(observed) is not int or not prior <= observed <= frame:
                raise ValueError('invalid item context chronology')
            prior = observed
        request = requests[-1]
        if not since < request['frame'] <= frame or any(type(request[key]) is not int or request[key] != spec[key] for key in ('item', 'heap')):
            raise ValueError('wrong or stale last item context')
        path = Path(point['screenshot']).resolve(strict=True)
        if not path.is_relative_to(BUILD_ROOT.resolve()):
            raise ValueError('screenshot outside work/build')
        result = analyze_png(str(path))
        result.update(frame=frame, since_frame=since, item=request['item'],
                      heap=request['heap'], request_frame=request['frame'])
        return result
    except (KeyError, TypeError, ValueError, IndexError, OSError) as exc:
        return {'status': 'incomplete', 'error': str(exc)}


def evaluate(config, runs):
    """Recompute proof from current screenshot bytes and raw checkpoint context."""
    try:
        validate_expectations(config)
    except ValueError as exc:
        return {'status': 'incomplete', 'error': str(exc), 'checkpoints': {}}
    if not config:
        return {'status': 'not_configured', 'checkpoints': {}}
    proofs = {}
    for name, spec in config.items():
        pair = {lang: _checkpoint(runs.get(lang, {}), name, spec) for lang in ('zh', 'en')} if isinstance(runs, dict) else {lang: {'status': 'incomplete'} for lang in ('zh', 'en')}
        zh, en = pair['zh']['status'], pair['en']['status']
        status = 'passed' if zh == en == 'present' else 'failed' if zh == 'present' and en == 'blank' else 'incomplete'
        proofs[name] = {'status': status, 'evidence': pair}
    statuses = [proof['status'] for proof in proofs.values()]
    status = 'failed' if 'failed' in statuses else 'incomplete' if 'incomplete' in statuses else 'passed'
    return {'status': status, 'checkpoints': proofs}


def evidence_status(entry):
    """Gate consumer recomputes metrics and rejects edited/deleted evidence."""
    if not isinstance(entry, dict):
        return 'incomplete'
    config = entry.get('rendering_expectations')
    fresh = evaluate(config, entry.get('runs'))
    if entry.get('rendering_status') != fresh['status'] or entry.get('rendering_evidence') != fresh:
        return 'incomplete'
    return fresh['status']

"""Insert a reviewed pure illustration without breaking its semantic paragraph."""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
from PIL import Image

def insert_inline_figure(hwp, block: dict, *, asset_root: Path, context: dict) -> dict:
    if block.get('type') != 'figure' or block.get('placement') != 'inline':
        raise ValueError('INLINE_FIGURE_PLACEMENT_REQUIRED')
    if block.get('allowed') is not True or block.get('reason') not in {
        'pure_graph', 'pure_geometry', 'pure_illustration', 'pure_adjacency_illustration'
    } or block.get('representation') in {'native_semantic', 'semantic_description'}:
        raise ValueError('INLINE_FIGURE_NOT_APPROVED')
    path = (asset_root / block['path']).resolve()
    payload = path.read_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    if sha != block.get('sha256'):
        raise ValueError('INLINE_FIGURE_HASH_MISMATCH')
    width = float(block['width_mm'])
    if not math.isfinite(width) or width <= 0:
        raise ValueError('INLINE_FIGURE_INVALID_WIDTH')
    with Image.open(path) as picture:
        pixels = picture.size
        picture.verify()
    height = width * pixels[1] / pixels[0]
    result = hwp.insert_picture(str(path), treat_as_char=True, embedded=True,
                                sizeoption=1, width=width, height=height)
    if result is False:
        raise RuntimeError('INLINE_FIGURE_INSERT_FAILED')
    # Match the established native figure cursor-collapse path, without its
    # paragraph break or style change. The following segment stays in this p.
    hwp.MoveParaEnd()
    return {**context, 'path': str(path), 'sha256': sha, 'pixels': list(pixels),
            'reason': block['reason'], 'figure_id': block.get('figure_id'),
            'source_region': block.get('source_region'), 'placement': 'inline',
            'width_mm': width, 'height_mm': height}

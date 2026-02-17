import tempfile
import base64
from pathlib import Path
from typing import Optional

try:
    from .generate import make_image
except Exception:
    from generate import make_image


def generate_png_base64(payload_text: str, rings: int = 14, sectors: int = 40, size: int = 1300, quality: int = 95, connect_dots: bool = False, connect_style: str = 'mesh', transparent: Optional[int] = 70, bank: Optional[str] = None) -> str:
    payload_bytes = payload_text.encode('utf-8')
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
        tmp_path = Path(tf.name)
    try:
        make_image(payload_bytes, str(tmp_path), rings=rings, sectors=sectors, size=size, quality=quality, connect_dots=connect_dots, connect_style=connect_style, transparent=transparent, bank=bank)
        b = tmp_path.read_bytes()
        return base64.b64encode(b).decode('ascii')
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

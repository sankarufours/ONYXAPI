from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
try:
    from . import generator
    from . import decoder
except Exception:
    import generator
    import decoder
import base64
from datetime import datetime
from pathlib import Path

app = FastAPI(title="ONYX Polar API", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DecodeRequest(BaseModel):
    image_base64: str
    color_mode: Optional[str] = 'cyan'
    thresh: Optional[int] = 100
    patch: Optional[int] = 6
    rings: Optional[int] = 14
    sectors: Optional[int] = 40
    size: Optional[int] = 1300


class DecodeResponse(BaseModel):
    payload: Optional[str]
    error: Optional[str]


class GenerateRequest(BaseModel):
    payload: str
    rings: Optional[int] = 14
    sectors: Optional[int] = 40
    transparent: Optional[int] = 70
    size: Optional[int] = 1300
    quality: Optional[int] = 95
    bank: Optional[str] = ''


class GenerateResponse(BaseModel):
    image_base64: str


@app.post('/generate', response_model=GenerateResponse)
def api_generate(req: GenerateRequest):
    try:
        b64 = generator.generate_png_base64(req.payload, rings=req.rings, sectors=req.sectors, size=req.size, quality=req.quality, connect_dots=False, transparent=req.transparent, bank=req.bank)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GenerateResponse(image_base64=b64)


@app.post('/decode', response_model=DecodeResponse)
def api_decode(req: DecodeRequest):
    try:
        save_dir = Path(__file__).resolve().parent / 'received_images'
        save_dir.mkdir(parents=True, exist_ok=True)
        b64 = req.image_base64
        if b64.startswith('data:'):
            b64 = b64.split(',', 1)[1]
        img_bytes = base64.b64decode(b64)
        ts = datetime.utcnow().strftime('%Y%m%dT%H%M%S%f')
        fname = f'recv_{ts}.jpg'
        fpath = save_dir / fname
        with open(fpath, 'wb') as f:
            f.write(img_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'failed_saving_image: {e}')

    text, err = decoder.decode_base64_image(req.image_base64, color_mode=req.color_mode, thresh=req.thresh, patch=req.patch, rings=req.rings, sectors=req.sectors, size=req.size)
    if err:
        return DecodeResponse(payload=None, error=err)
    return DecodeResponse(payload=text, error=None)

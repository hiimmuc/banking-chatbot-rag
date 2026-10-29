"""MinerU2.5-Pro VLM OCR via transformers. Usage: ocr_mineru.py OUT_DIR PNG..."""
import json, os, sys, pathlib, time, torch
from PIL import Image
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
from mineru_vl_utils import MinerUClient

MODEL = "opendatalab/MinerU2.5-Pro-2604-1.2B"
DEV = os.environ.get("RAG_DEVICE", "cuda")
# mps: device_map segfaults while loading weights on Apple Silicon, so load on CPU then move
model = Qwen2VLForConditionalGeneration.from_pretrained(MODEL, dtype=torch.bfloat16 if DEV == "cuda" else torch.float16, device_map=DEV if DEV == "cuda" else None)
if DEV != "cuda": model = model.to(DEV)
proc = AutoProcessor.from_pretrained(MODEL, use_fast=True)
client = MinerUClient(backend="transformers", model=model, processor=proc)

out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
for p in map(pathlib.Path, sys.argv[2:]):
    if (out / f"{p.stem}.md").exists() and (out / f"{p.stem}.json").exists(): continue
    t = time.time()
    blocks = client.two_step_extract(Image.open(p).convert("RGB"))
    md = "\n\n".join(b["content"] for b in blocks if b.get("content"))
    (out / f"{p.stem}.md").write_text(md, encoding="utf-8")
    # normalized [x1,y1,x2,y2] boxes: the source popup draws the cited blocks on the page image
    (out / f"{p.stem}.json").write_text(json.dumps([{"bbox": b["bbox"], "type": b["type"], "content": b.get("content")} for b in blocks], ensure_ascii=False), encoding="utf-8")
    print("ok", p.name, f"{time.time()-t:.1f}s", len(blocks), "blocks", flush=True)

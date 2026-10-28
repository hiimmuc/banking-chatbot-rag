"""OCR page images with a Vintern model; skips pages already done.

    HF_HOME=~/huggingface python eval/ocr_vintern.py 5CD-AI/Vintern-1B-v3_5 cuda data/ocr_vintern1b data/pages/*.png
Needs transformers 4.46 + timm + einops + accelerate (separate venv from the app).
"""
import pathlib, sys, time
import torch, torchvision.transforms as T
from PIL import Image
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoModel, AutoTokenizer

model_id, device, out_dir, *pages = sys.argv[1:]
SIZE, MEAN, STD = 448, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
PROMPT = "<image>\nTrích xuất toàn bộ văn bản trong ảnh thành Markdown, giữ nguyên bảng và số liệu."
tf = T.Compose([T.Lambda(lambda im: im.convert("RGB")), T.Resize((SIZE, SIZE), interpolation=InterpolationMode.BICUBIC), T.ToTensor(), T.Normalize(MEAN, STD)])


def tiles(im, max_num):
    w, h = im.size
    ratios = sorted({(i, j) for n in range(1, max_num + 1) for i in range(1, n + 1) for j in range(1, n + 1) if 1 <= i * j <= max_num}, key=lambda r: r[0] * r[1])
    best = min(ratios, key=lambda r: (abs(w / h - r[0] / r[1]), -r[0] * r[1] if w * h > 0.5 * SIZE * SIZE * r[0] * r[1] else 0))
    big = im.resize((SIZE * best[0], SIZE * best[1]))
    out = [big.crop(((k % best[0]) * SIZE, (k // best[0]) * SIZE, (k % best[0] + 1) * SIZE, (k // best[0] + 1) * SIZE)) for k in range(best[0] * best[1])]
    return out + ([im.resize((SIZE, SIZE))] if len(out) > 1 else [])


dtype = torch.bfloat16
model = AutoModel.from_pretrained(model_id, torch_dtype=dtype, low_cpu_mem_usage=True, trust_remote_code=True).eval().to(device)
tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True, use_fast=False)
out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
for page in map(pathlib.Path, pages):
    if (out / f"{page.stem}.md").exists():
        continue
    px = torch.stack([tf(t) for t in tiles(Image.open(page), 6)]).to(dtype).to(device)
    t0 = time.time()
    with torch.no_grad():
        text = model.chat(tok, px, PROMPT, dict(max_new_tokens=2500, do_sample=False, num_beams=1, repetition_penalty=1.1))
    (out / f"{page.stem}.md").write_text(text, encoding="utf-8")
    print("ok", page.name, f"{time.time()-t0:.1f}s", len(text), "chars", flush=True)

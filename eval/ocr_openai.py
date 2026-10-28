"""OCR page images with an OpenAI vision model; skips pages already done. Sends page images to OpenAI.

    python eval/ocr_openai.py gpt-4.1-mini data/ocr_openai data/pages/*.png
"""
import base64, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from openai import OpenAI
from app import config
from app.ocr import GEMINI_PROMPT

model, out_dir, *pages = sys.argv[1:]
client = OpenAI(api_key=config.env("OPENAI_API_KEY"), timeout=120)
out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
tokens = [0, 0]
for page in map(pathlib.Path, pages):
    if (out / f"{page.stem}.md").exists():
        continue
    img = base64.b64encode(page.read_bytes()).decode()
    t0 = time.time()
    r = client.chat.completions.create(model=model, temperature=0, max_completion_tokens=4000, messages=[{"role": "user", "content": [
        {"type": "text", "text": GEMINI_PROMPT + " Do not pad table cells with spaces."}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}", "detail": "high"}}]}])
    (out / f"{page.stem}.md").write_text(r.choices[0].message.content.strip(), encoding="utf-8")
    tokens[0] += r.usage.prompt_tokens; tokens[1] += r.usage.completion_tokens
    print("ok", page.name, f"{time.time()-t0:.1f}s", tokens, flush=True)

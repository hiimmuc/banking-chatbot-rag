"""End-to-end chat eval against the running API. Checks mode tag, fact in answer, cited ids valid, unverified-number flag."""
import json, sys, re, pathlib, httpx
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.textnorm import fold
import os
BASE = os.environ.get("BASE", "http://localhost:8080"); AUTH = (os.environ["APP_USER"], os.environ["APP_PASSWORD"]) if os.environ.get("APP_PASSWORD") else None
provider = sys.argv[1] if len(sys.argv) > 1 else "qwen"
qs = json.load(open(pathlib.Path(__file__).with_name("questions.json")))
def ask(q):
    ev, data = None, {"text": "", "mode": None, "sources": [], "verify": [], "error": None, "top": None, "versions": []}
    with httpx.stream("POST", f"{BASE}/api/chat", auth=AUTH, json={"messages": [{"role": "user", "content": q}], "provider": provider, "max_output_tokens": 800}, timeout=300) as r:
        if r.status_code != 200:
            raise SystemExit(f"HTTP {r.status_code}: set APP_USER/APP_PASSWORD if the server has auth on")
        for line in r.iter_lines():
            if line.startswith("event: "): ev = line[7:]
            elif line.startswith("data: "):
                d = json.loads(line[6:])
                if ev == "delta": data["text"] += d["text"]
                elif ev == "mode": data["mode"] = d["mode"]
                elif ev == "sources": data["sources"] = [s["id"] for s in d["sources"]]; data["top"] = d["sources"][0]["score"] if d["sources"] else None; data["versions"] = d.get("versions", []); data["src_docs"] = [x["documentId"] for x in d["sources"]]
                elif ev == "verify": data["verify"] += d.get("unverified") or (["UNCITED"] if d.get("uncited") else [])
                elif ev == "error": data["error"] = d["message"]
    return data
fails = 0
for i, t in enumerate(qs, 1):
    d = ask(t["q"]); probs = []
    if d["error"]: probs.append("error:" + d["error"])
    cited = set(re.findall(r"\[(S\d+)\]", d["text"]))
    if cited - set(d["sources"]): probs.append(f"invalid cites {cited - set(d['sources'])}")
    if t.get("expect_mode") and d["mode"] not in t["expect_mode"]: probs.append(f"mode={d['mode']} want {t['expect_mode']}")
    for want in t.get("answer_facts") or [t.get("fact")]:
        if want and fold(want).replace(" ", "") not in fold(d["text"]).replace(" ", ""): probs.append(f"fact {want} missing")
    if t.get("expect_versions") and not set(t["expect_versions"]) <= set(d.get("src_docs", [])): probs.append(f"versions {t['expect_versions']} not all in sources")
    if t.get("expect_versions") and not d["versions"]: probs.append("no versions event content")
    if t["docs"] and not t.get("expect_mode") and not cited: probs.append("no citation")
    if d["verify"]: probs.append(f"unverified numbers {d['verify']}")
    fails += bool(probs)
    print(f"{'PASS' if not probs else 'FAIL'} #{i} mode={d['mode']} top={d['top']} cites={sorted(cited)} {probs}\n    {d['text'][:220]!r}")
print(f"\n{len(qs)-fails}/{len(qs)} chat pass ({provider})"); sys.exit(1 if fails else 0)

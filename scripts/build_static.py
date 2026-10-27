"""Build the static UI for a host that is not the API (Cloudflare Pages, GitHub Pages).

    python scripts/build_static.py --api https://rag.example.ts.net --out dist
"""
import argparse, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
API_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d+)?$|^http://(localhost|127\.0\.0\.1)(:\d+)?$")  # plain http only for local testing


def csp(api: str) -> str:
    return (f"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' {api} data:; connect-src {api}; "
            f"frame-src {api}; object-src 'none'; base-uri 'none'; form-action 'none'")


def build(api: str, out: pathlib.Path) -> None:
    api = api.rstrip("/")
    if not API_RE.match(api):
        sys.exit(f"--api must be an https origin (or http://localhost for tests), got {api!r}")
    if ROOT not in out.resolve().parents:
        sys.exit("--out must be a directory inside the repository")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for f in [*WEB.glob("*.js"), WEB / "style.css"]:
        shutil.copy(f, out / f.name)
    (out / "config.js").write_text(f"export const API_BASE = {api!r};\n".replace("'", '"'), encoding="utf-8")
    meta = f'<meta http-equiv="Content-Security-Policy" content="{csp(api)}">'
    html = (WEB / "index.html").read_text(encoding="utf-8").replace('<meta charset="utf-8">', f'<meta charset="utf-8">\n{meta}', 1)
    (out / "index.html").write_text(html, encoding="utf-8")
    # Cloudflare Pages reads _headers; GitHub Pages cannot set headers, so the meta CSP above is the fallback there.
    (out / "_headers").write_text("/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  X-Frame-Options: DENY\n"
                                  f"  Permissions-Policy: camera=(), microphone=(), geolocation=()\n  Content-Security-Policy: {csp(api)}\n", encoding="utf-8")
    (out / ".nojekyll").touch()
    print(f"built {out.relative_to(ROOT)} for API {api}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="public origin of the API host, e.g. https://box.tailnet.ts.net")
    ap.add_argument("--out", default="dist", type=pathlib.Path)
    args = ap.parse_args()
    build(args.api, ROOT / args.out if not args.out.is_absolute() else args.out)

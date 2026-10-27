import importlib.util, pathlib, shutil
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_static", ROOT / "scripts" / "build_static.py")
build_static = importlib.util.module_from_spec(spec); spec.loader.exec_module(build_static)


@pytest.fixture
def out():
    path = ROOT / "dist-test"
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_build_pins_api_origin_in_config_and_csp(out):
    build_static.build("https://api.example.com/", out)
    assert (out / "config.js").read_text() == 'export const API_BASE = "https://api.example.com";\n'
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'http-equiv="Content-Security-Policy"' in html and "connect-src https://api.example.com;" in html
    assert "unsafe-inline" not in html
    headers = (out / "_headers").read_text()
    assert "frame-src https://api.example.com" in headers and (out / ".nojekyll").exists()
    assert {p.name for p in out.glob("*.js")} >= {"app.js", "api.js", "robot.js", "util.js", "config.js"}


@pytest.mark.parametrize("api", ["http://evil.example.com", "https://a.com/path", "ftp://x", "javascript:alert(1)", "https://a.com; script-src *"])
def test_build_rejects_unsafe_api_origins(api, out):
    with pytest.raises(SystemExit):
        build_static.build(api, out)


def test_build_refuses_output_outside_repo(tmp_path):
    with pytest.raises(SystemExit):
        build_static.build("https://api.example.com", tmp_path / "x")

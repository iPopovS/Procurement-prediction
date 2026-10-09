"""Guards for Docker-readiness: pinned training versions and files the image needs."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Versions the artifact was trained with (task description).
TRAINING_PINS = {
    "joblib": "1.6.0", "lightgbm": "4.7.0", "numpy": "2.4.6", "pandas": "3.0.5",
    "scikit-learn": "1.9.0", "scipy": "1.17.1", "pyarrow": "25.0.1",
}


def pins() -> dict[str, str]:
    out = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s#]+)", line.strip())
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def test_model_stack_is_pinned_to_training_versions():
    p = pins()
    for name, ver in TRAINING_PINS.items():
        assert p.get(name) == ver, f"{name} must be pinned to {ver}"


def test_every_requirement_is_exactly_pinned():
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            assert "==" in line, f"unpinned requirement: {line}"


def test_runtime_files_the_image_needs_exist():
    for rel in ("app/data/regions.json", "app/static/index.html", "app/static/vendor/maplibre-gl.js",
                "app/static/vendor/maplibre-gl.css", "app/static/data/regions.geojson", "app/static/data/countries.geojson",
                "app/static/fonts/ibm-plex-sans-cyrillic-400-normal.woff2"):
        assert (ROOT / rel).stat().st_size > 0, rel


def test_dockerignore_does_not_exclude_app_resources():
    patterns = [ln.strip() for ln in (ROOT / ".dockerignore").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    for bad in ("data", "static", "app", "*.json", "**/data", "**/*.json"):
        assert bad not in patterns


def test_static_assets_do_not_reference_external_hosts():
    """Vendored everything: only the configurable tile URL may point outside."""
    for f in (ROOT / "app/static").rglob("*"):
        if f.suffix in {".html", ".css"} or (f.suffix == ".js" and "vendor" not in f.parts):
            text = f.read_text(encoding="utf-8")
            hosts = set(re.findall(r"""(?:src|href)=["']https?://([^/"']+)""", text) + re.findall(r"url\(\s*https?://([^/)'\"]+)", text))
            assert not hosts, f"{f.name} loads from {hosts}"

"""Model folder exported from the notebook / downloaded from Hugging Face."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.ml import manifest as mf
from app.ml import pipeline as pl
from app.ml.predictor import PredictionService, raw_to_frame
from app.services.mapper import build_raw
from tests.conftest import ROOT, load_fixture


# ------------------------------------------------------------------ helpers
def make_folder(tmp_path: Path, **manifest_extra) -> Path:
    folder = tmp_path / "hf_model"
    folder.mkdir()
    for i, name in enumerate(mf.REQUIRED_FILES):
        (folder / name).write_bytes(f"content-{i}".encode() * 50)
    manifest = {"version": "v1", "trained_through": "2026-06-02 20:58:45", **manifest_extra,
                "files": {n: mf.sha256_file(folder / n) for n in sorted(p.name for p in folder.iterdir())}}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


# ------------------------------------------------------------------ manifest (no model needed)
def test_valid_folder_passes(tmp_path):
    folder = make_folder(tmp_path)
    mf.verify_files(folder, mf.read_manifest(folder))


def test_checksum_mismatch_is_reported_by_file_name(tmp_path):
    folder = make_folder(tmp_path)
    (folder / "clf.txt").write_bytes(b"truncated")
    with pytest.raises(mf.ModelFilesError, match=r"clf\.txt: checksum mismatch"):
        mf.verify_files(folder, mf.read_manifest(folder))


def test_missing_file_and_unlisted_file(tmp_path):
    folder = make_folder(tmp_path)
    (folder / "store.parquet").unlink()
    m = mf.read_manifest(folder)
    del m["files"]["l2.txt"]
    with pytest.raises(mf.ModelFilesError) as e:
        mf.verify_files(folder, m)
    assert "store.parquet: file is missing" in str(e.value) and "l2.txt: not listed" in str(e.value)


def test_manifest_problems(tmp_path):
    with pytest.raises(mf.ModelFilesError, match="manifest.json not found"):
        mf.read_manifest(tmp_path)
    (tmp_path / "manifest.json").write_text("{nope")
    with pytest.raises(mf.ModelFilesError, match="not valid JSON"):
        mf.read_manifest(tmp_path)
    (tmp_path / "manifest.json").write_text('{"version": "v1"}')
    with pytest.raises(mf.ModelFilesError, match="no 'files'"):
        mf.read_manifest(tmp_path)


def test_library_version_warnings():
    import lightgbm
    assert mf.library_warnings({"lightgbm": lightgbm.__version__}) == []
    w = mf.library_warnings({"lightgbm": "0.0.1", "sklearn": "0.0.2"})
    assert any("lightgbm" in x and "0.0.1" in x for x in w) and any("scikit-learn" in x for x in w)


def test_missing_model_path_gives_actionable_error(tmp_path):
    svc = PredictionService(tmp_path / "nope")
    svc._load()
    st = svc.status()
    assert st["state"] == "error" and "Hugging Face" in st["error"] and not st["ready"]
    # predictions degrade to a readable reason instead of crashing
    res = svc.predict_one(build_raw(load_fixture("gosplan_ezk_purchase.json")))
    assert not res.ok and "failed to load" in res.reason


def test_corrupted_folder_is_rejected_before_anything_is_loaded(tmp_path):
    folder = make_folder(tmp_path)
    (folder / "config.joblib").write_bytes(b"x")
    with pytest.raises(mf.ModelFilesError, match="checksum mismatch"):
        pl.ModelBundle.load(folder)
    with pytest.raises(mf.ModelFilesError, match="not found"):
        pl.ModelBundle.load(tmp_path / "missing")


# ------------------------------------------------------------------ download script (mocked Hugging Face)
def load_script():
    spec = importlib.util.spec_from_file_location("download_model", ROOT / "scripts" / "download_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_download_script_downloads_verifies_and_reports(tmp_path, monkeypatch, capsys):
    hub = pytest.importorskip("huggingface_hub")
    (tmp_path / "remote").mkdir()
    src = make_folder(tmp_path / "remote")
    calls = {}

    def fake_snapshot(**kw):
        calls.update(kw)
        shutil.copytree(src, kw["local_dir"], dirs_exist_ok=True)
        return kw["local_dir"]

    monkeypatch.setattr(hub, "snapshot_download", fake_snapshot)
    monkeypatch.setenv("HF_TOKEN", "hf_secret")
    out = tmp_path / "artifacts" / "hf_model"
    assert load_script().main(["--repo", "me/repo", "--revision", "v1", "--out", str(out)]) == 0
    assert calls["repo_id"] == "me/repo" and calls["revision"] == "v1" and calls["repo_type"] == "model" and calls["token"] == "hf_secret"
    text = capsys.readouterr().out
    assert "OK: model v1" in text and "hf_secret" not in text  # the token is never printed


def test_download_script_reports_private_repo_and_bad_files_readably(tmp_path, monkeypatch, capsys):
    hub = pytest.importorskip("huggingface_hub")
    from huggingface_hub.errors import RepositoryNotFoundError

    def not_found(**kw):
        raise RepositoryNotFoundError("401 Unauthorized", response=SimpleNamespace(headers={}, status_code=401, request=None))

    monkeypatch.setattr(hub, "snapshot_download", not_found)
    assert load_script().main(["--repo", "me/private", "--out", str(tmp_path / "o")]) == 1
    assert "HF_TOKEN" in capsys.readouterr().err

    def corrupt(**kw):
        (tmp_path / "bad").mkdir(exist_ok=True)
        folder = make_folder(tmp_path / "bad")
        (folder / "clf.txt").write_bytes(b"partial")
        return str(folder)

    monkeypatch.setattr(hub, "snapshot_download", corrupt)
    assert load_script().main(["--repo", "me/repo", "--out", str(tmp_path / "o2")]) == 1
    assert "clf.txt: checksum mismatch" in capsys.readouterr().err


def test_download_script_requires_repo(monkeypatch):
    pytest.importorskip("huggingface_hub")
    monkeypatch.delenv("HF_REPO_ID", raising=False)
    with pytest.raises(SystemExit) as e:
        load_script().main([])
    assert e.value.code == 2


# ------------------------------------------------------------------ real folder (heavy)
def real_folder() -> Path | None:
    import os
    for cand in (os.getenv("HF_MODEL_DIR"), os.getenv("PREDICTOR_ARTIFACT"), str(ROOT / "artifacts" / "hf_model")):
        if cand and Path(cand).is_dir() and (Path(cand) / "manifest.json").exists():
            return Path(cand)
    return None


def legacy_file() -> Path | None:
    import os
    for cand in (os.getenv("LEGACY_JOBLIB"), str(ROOT / "artifacts" / "predictor.joblib")):
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


needs_folder = pytest.mark.skipif(real_folder() is None, reason="model folder not available (set HF_MODEL_DIR)")
needs_both = pytest.mark.skipif(real_folder() is None or legacy_file() is None, reason="needs the folder and the legacy predictor.joblib")


@pytest.fixture(scope="module")
def folder_bundle():
    return pl.ModelBundle.load(real_folder())


@pytest.mark.model
@needs_folder
def test_folder_loads_with_meta_and_status(folder_bundle):
    assert folder_bundle.meta.format == "folder" and folder_bundle.meta.version
    svc = PredictionService("unused")
    svc.set_bundle(folder_bundle)
    st = svc.status()
    assert st["ready"] and st["model_version"] == folder_bundle.meta.version and st["model_format"] == "folder"
    assert st["history_until"].startswith("2026") and st["library_warnings"] == []
    assert list(folder_bundle.clf.feature_name_) == list(folder_bundle.FEATS)


@pytest.mark.model
@needs_folder
def test_known_example_through_the_folder_model(folder_bundle):
    ex = load_fixture("gosplan_ezk_purchase.json")
    r = folder_bundle.predict(raw_to_frame([build_raw(ex)])).iloc[0]
    assert r["ratio_median"] == pytest.approx(0.775, abs=1e-9)
    assert r["predicted_price"] == pytest.approx(699041.475, rel=1e-6)
    r = folder_bundle.predict(raw_to_frame([build_raw({**ex, "object_info": None})])).iloc[0]
    assert r["ratio_median"] == pytest.approx(0.92, abs=1e-9)


@pytest.mark.model
@needs_both
def test_folder_model_is_equivalent_to_legacy_joblib(folder_bundle):
    from tests.test_pipeline_parity import sample_raws

    legacy = pl.ModelBundle.load(legacy_file())
    rows = sample_raws(legacy)
    rs = np.random.RandomState(5)
    rows = [{**rows[i % len(rows)], "purchase_number": f"{i:019d}", "max_price": float(rs.choice([5e4, 4e5, 2e6, 9e7])),
             "published_at": f"2026-0{1 + rs.randint(5)}-{1 + rs.randint(27):02d}T08:00:00"} for i in range(120)]
    df = raw_to_frame([build_raw(r) for r in rows])
    a, b = legacy.predict(df), folder_bundle.predict(df)
    for col in ("p_low", "p_nodrop", "ratio_median", "ratio_mean", "predicted_price", "predicted_price_for_sums"):
        np.testing.assert_allclose(a[col].to_numpy(), b[col].to_numpy(), rtol=1e-6, err_msg=col)
    assert (a["ratio_median"].to_numpy() == b["ratio_median"].to_numpy()).all()
    # float32 `ratio` in the exported store is the only numerical difference (~5e-9 on 3 history features)
    Xa, Xb = legacy.build_X(df), folder_bundle.build_X(df)
    for c in ("r_ratio", "s2_ratio", "s5_ratio", "r_low", "s2_n"):
        np.testing.assert_allclose(Xa[c].astype(float).to_numpy(), Xb[c].astype(float).to_numpy(), rtol=0, atol=1e-7, equal_nan=True)

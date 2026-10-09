"""Download the model folder from Hugging Face (private repo) and verify its checksums.

    pip install huggingface_hub          # only needed on the machine that downloads, not in Docker
    export HF_TOKEN=hf_xxx               # read token for the private repo, or run `hf auth login` once
    python scripts/download_model.py --repo your-username/procurement-price-artifacts --revision v1

Defaults come from the environment: HF_REPO_ID, HF_REVISION (default v1), HF_TOKEN.
The folder is written to artifacts/hf_model, which docker-compose mounts read-only.
Re-running only fetches files that changed. Pin ``--revision`` to a tag or commit hash.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ml import manifest as mf  # noqa: E402  (stdlib-only module, no pandas/LightGBM import)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.getenv("HF_REPO_ID"), help="Hugging Face repo id, e.g. user/procurement-price-artifacts")
    ap.add_argument("--revision", default=os.getenv("HF_REVISION", "v1"), help="tag, branch or commit hash (default: v1)")
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "hf_model"), help="target folder")
    args = ap.parse_args(argv)
    if not args.repo:
        ap.error("--repo is required (or set HF_REPO_ID)")

    try:
        import huggingface_hub
        from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError, RevisionNotFoundError
    except ImportError:
        print("huggingface_hub is not installed. Run: pip install huggingface_hub", file=sys.stderr)
        return 2

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or None  # None -> credentials saved by `hf auth login`
    try:
        path = huggingface_hub.snapshot_download(
            repo_id=args.repo, repo_type="model", revision=args.revision, token=token, local_dir=args.out
        )
    except RepositoryNotFoundError:
        print(f"Repository '{args.repo}' not found or not accessible. For a private repo set HF_TOKEN to a token "
              "with read access (huggingface.co > Settings > Access Tokens) and check the repo id.", file=sys.stderr)
        return 1
    except RevisionNotFoundError:
        print(f"Revision '{args.revision}' does not exist in '{args.repo}' (was the tag created?).", file=sys.stderr)
        return 1
    except HfHubHTTPError as exc:
        print(f"Hugging Face returned an error: {exc}", file=sys.stderr)
        return 1

    try:
        manifest = mf.read_manifest(path)
        mf.verify_files(path, manifest)
    except mf.ModelFilesError as exc:
        print(f"Downloaded, but verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"OK: model {manifest.get('version')} (history through {manifest.get('trained_through')}) in {path}")
    for w in mf.library_warnings(manifest):
        print(f"WARNING: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

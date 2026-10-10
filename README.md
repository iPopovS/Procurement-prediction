# Tender Price Predictor

Predicts the final winning price of Russian public procurements (**EF / EZK / EZT**, 44-FZ) at the moment the notice is published, and shows tenders on an interactive map.

* **Backend** – FastAPI + SQLite (WAL). Fetches tenders from GosPlan, stores them, runs the already-trained model.
* **Model** – the unchanged model from `model_train.ipynb`, exported as a small folder (`hf_model/`: three LightGBM text models, text/config joblibs, history `store.parquet`, `manifest.json`) and published to a private Hugging Face repo. Nothing is retrained.
* **Frontend** – static single page served by the same container: MapLibre GL map (no Leaflet), clustering, filters, global search, details panel, upload dialog. All JS/CSS/fonts/GeoJSON are vendored; the base-map tiles are the only optional external resource.

## Quick start (Docker)

```bash
cd tender-predictor
# 1. get the model folder from Hugging Face into ./artifacts/hf_model  (see "Model files" below)
pip install huggingface_hub==2.2.0                        # download tool only, not part of the image
export HF_TOKEN=hf_xxx                                    # read token for the private repo
python scripts/download_model.py --repo ArlandSol/procurement-price-artifacts --revision v1
# 2. run
cp .env.example .env                                      # optional
docker compose up --build -d
docker compose logs -f                                    # wait for "model ready" (about 1 minute)
```

Open <http://localhost:8000> (API docs: <http://localhost:8000/docs>).

The interface opens in **Russian by default**. Use the **RU / EN** buttons in the header to switch languages without reloading; the preference is saved in the browser. Interface labels, region names, dates, prices and application messages follow the selected language. Tender titles, organizer names, addresses and downloaded GosPlan JSON remain as supplied by the source. Technical diagnostics that are not recognized by the translation dictionary are kept verbatim.

The server answers immediately; the model and history indexes load in a background thread (≈ 25 s, ≈ 2.2 GB peak, ≈ 1.4 GB afterwards). Until then predictions return a readable "model is still loading" message / HTTP 503 and the header pill shows *Model loading*.

```bash
docker compose ps            # health state
docker compose down          # stop (data kept in the named volume tender-data)
docker compose down -v       # stop AND delete the database
```

Requires Docker Compose v2.24+ (optional `env_file`). Use a **named volume** for `/data` (as in the compose file); with a bind mount make the host folder writable by uid 10001.

## Configuration

All settings are environment variables (`.env.example` lists them; defaults in `app/config.py`).

| Variable | Default | Meaning |
|---|---|---|
| `GOSPLAN_BASE_URL` | `https://v2test.gosplan.info` (`https://v2.gosplan.info` if `GOSPLAN_API_KEY` is set) | GosPlan API root; an explicit value always wins |
| `GOSPLAN_API_KEY` | empty | optional API key, sent as the `apikey` header; switches the default server to production |
| `GOSPLAN_TIMEOUT` | `20` | seconds per HTTP attempt |
| `GOSPLAN_RETRIES` | `3` | extra attempts on timeout / 429 / 5xx (exponential backoff + jitter, honours `Retry-After`) |
| `GOSPLAN_BACKOFF` | `0.5` | base delay, seconds |
| `GOSPLAN_CONCURRENCY` | `8` | max parallel GosPlan requests (semaphore) |
| `MAX_BATCH_SIZE` | `1000` | max items per `POST /api/tenders` (the UI sends 25 at a time) |
| `MAP_TILE_URL` | OpenStreetMap raster | tile template; **set but empty = no tiles, fully offline** (borders only) |
| `MAP_TILE_ATTRIBUTION`, `MAP_TILE_MAX_ZOOM` | `© OpenStreetMap contributors`, `18` | |
| `DB_PATH` | `/data/tenders.db` | SQLite file (volume) |
| `ARTIFACT_PATH` | `/app/artifacts/hf_model` | model folder downloaded from Hugging Face (a legacy `predictor.joblib` file path also works) |
| `MODEL_AUTOLOAD` | `1` | `0` = do not load the model (UI/API without predictions) |
| `LOG_LEVEL` | `INFO` | |
| `HOST_PORT` | `8000` | host port in compose |

### GosPlan test vs. production server

By default the service uses the free test server `https://v2test.gosplan.info` (no key, same datasets as production, but limited to 10 requests/minute per IP). If you have an API key (see <https://gosplan.info/docs/>; the Telegram bot gives a 7-day trial), put it in `.env`:

```
GOSPLAN_API_KEY=your-key
```

The service then talks to `https://v2.gosplan.info` and sends the key in the `apikey` header. Restart the app (`docker compose up -d`) after changing `.env`. To use a key with another URL, set `GOSPLAN_BASE_URL` too.

The default OSM tile server has a usage policy (no heavy use, needs a real browser `Referer`); for production point `MAP_TILE_URL` at your own tile source.

## Model files (Hugging Face)

The model is **not** in the image or in this repo. It lives in your private Hugging Face repo (created by the notebook's export cell + `upload_folder`, tag `v1`) and is downloaded **on the host** into `artifacts/hf_model/`, which `docker-compose.yml` mounts read-only. The container therefore needs neither a Hugging Face token nor the `huggingface_hub` package.

```python
# minimal download (this is all scripts/download_model.py does, plus checksum verification)
from huggingface_hub import snapshot_download

snapshot_download(
    "your-username/procurement-price-artifacts",   # repo id
    repo_type="model",
    revision="v1",                                  # tag or commit hash: pin it, do not use "main"
    local_dir="artifacts/hf_model",
    token="hf_xxx",                                 # read token; or None after `hf auth login`
)
```

```bash
pip install huggingface_hub==2.2.0
export HF_TOKEN=hf_xxx            # huggingface.co > Settings > Access Tokens > "Read"; never commit it
python scripts/download_model.py --repo your-username/procurement-price-artifacts --revision v1
# -> OK: model v1 (history through 2026-06-02 20:58:45) in artifacts/hf_model
docker compose restart            # a running container reads the folder only at start-up
```

Expected folder (87 MB): `manifest.json  clf.txt  reg.txt  l2.txt  text.joblib  config.joblib  store.parquet`.

What the app checks when it loads the folder (`app/ml/manifest.py`):

* every file is listed in `manifest.json` and its **sha256 matches**, otherwise start-up fails with a readable error naming the file (incomplete download, edited file);
* installed `scikit-learn / lightgbm / pandas / numpy` versions vs. the ones recorded at export time: a difference is logged and shown in `/api/health` (`library_warnings`) and in the header pill tooltip, it does not block start-up;
* `/api/health` reports `model_version` (`v1`), `trained_through` and `history_until`.

To roll out a new model: export, `upload_folder`, `create_tag(..., "v2")`, then `python scripts/download_model.py --revision v2` and `docker compose restart`.

Security note: `text.joblib` and `config.joblib` are pickles and the manifest hashes only prove the download is intact, not who made it. Keep the repo private, pin `--revision`, and use a read-only token.

### What changed in the project for this format

| File | Change |
|---|---|
| `app/ml/pipeline.py` | `ModelBundle.load(path)` now takes the **folder** (or, as before, a `.joblib` file). New `_read_folder()`; new `BoosterModel` adapter so the three LightGBM `Booster`s expose `predict_proba` / `predict`. The notebook functions (`predict_X`, `build_X`, `history_features`, `mix_median`, ...) are **unchanged**. |
| `app/ml/manifest.py` | **new** – manifest reading, sha256 verification, library-version comparison (stdlib only). |
| `app/ml/predictor.py` | status now includes `model_version`, `trained_through`, `library_warnings`; "model not found" message points to the download step. |
| `app/config.py`, `Dockerfile`, `docker-compose.yml`, `.env.example` | default `ARTIFACT_PATH` is `/app/artifacts/hf_model` (was `.../predictor.joblib`). The `./artifacts:/app/artifacts:ro` mount is unchanged. |
| `scripts/download_model.py` | **new** – downloads the private repo at a pinned revision and verifies it. |
| `requirements-dev.txt` | `huggingface_hub==2.2.0` (download script only). `requirements.txt` is unchanged: `pyarrow` (needed for `store.parquet`) was already pinned. |
| `app/static/js/main.js` | status-pill tooltip shows the model version. |
| `tests/` | `test_model_folder.py` (manifest, corruption, mocked download, folder loads, folder ≡ legacy joblib); `conftest.py` finds the folder or the legacy file. |

### Verified equivalence with the old `predictor.joblib`

Using your export cell on the old artifact: the three text models give **bit-identical** outputs to the sklearn wrappers (max difference 0.0, including categoricals and NaNs). The only numerical difference is the `float32` cast of `store["ratio"]` (max 3e-8 per row), which moves three history features by ≈ 5e-9. On 200 varied tenders all six outputs (`p_low`, `p_nodrop`, `ratio_median`, `ratio_mean`, both prices) were identical, and the sample tender gives ₽699,041.475 either way. Loading is also faster (≈ 25 s vs ≈ 50 s) and uses less memory.

## Using the UI

* **Upload tenders** – paste purchase numbers or drop a CSV/TXT/JSON file, tick *Predict prices immediately*, get a per-item report (stored / updated / skipped / failed, winner price, prediction or the reason there is none).
* **Map** – one donut per location, diameter grows with the number of tenders, colour split shows the mix (*Colour by*: status or purchase type). Clusters expand on click; hover shows a summary; click a location to open the record (one tender) or a searchable list (several).
* **Search** (top bar) – number, title, organizer name/ID, KTRU/OKPD2 codes, plan number, IKZ, address text. Respects the active filters. Picking a result opens its details and flies to it.
* **Filters** – status, purchase type, region, organizer, publication date, max price, "on map / not on map". Everything (map, counters, search, selector lists) updates server-side.
* **Details** – purchase number button (downloads the raw GosPlan JSON), title, organizer, dates (UTC), prices, codes, price ladder (predicted vs. winner vs. max price), outcome probabilities, history depth, warnings, *Generate price prediction*.

## API

Interactive docs at `/docs` (OpenAPI at `/openapi.json`).

```bash
# upload by purchase number, fetch winner price, predict immediately
curl -X POST localhost:8000/api/tenders -H 'Content-Type: application/json' \
  -d '{"purchase_numbers":["0320300101526000015"],"predict":true}'

# upload a full GosPlan record (optionally with a top-level "winner_price")
curl -X POST localhost:8000/api/tenders -H 'Content-Type: application/json' \
  -d '{"records":[ { ...GET /fz44/purchases/{n} JSON... } ],"predict":true,"fetch_winner":false}'

# file upload (CSV with a purchase_number column [+ optional winner_price], TXT one per line, or JSON)
curl -F file=@numbers.csv -F predict=true localhost:8000/api/tenders/upload

curl 'localhost:8000/api/tenders?q=трубка&status=winner&region=25&purchase_type=epNotificationEZK2020&price_min=100000&sort=price_desc&limit=20'
curl localhost:8000/api/tenders/0320300101526000015
curl -X POST localhost:8000/api/tenders/0320300101526000015/predict
curl -X POST localhost:8000/api/tenders/0320300101526000015/winner      # re-check protocols
curl -OJ localhost:8000/api/tenders/0320300101526000015/download        # raw GosPlan JSON -> 0320300101526000015.json
curl -X DELETE localhost:8000/api/tenders/0320300101526000015
curl localhost:8000/api/filters            # filter fields and values generated from the stored data
curl localhost:8000/api/summary            # counters for the same filter parameters
curl localhost:8000/api/map/points         # aggregated GeoJSON, one feature per location
curl localhost:8000/api/health
```

Batch uploads never fail as a whole: the response has `summary` plus one `results[]` entry per item with `status` (`created|updated|skipped|failed`), `error`/`error_kind` (`not_found`, `timeout`, `unavailable`, `bad_response`, `invalid`, …), `winner_price` and a `prediction` block (`ok` + price, or `failed` + readable `reason`).

Filter parameters (shared by `/api/tenders`, `/api/summary`, `/api/map/points`): `q`, `status` (`winner|predicted|not_predicted`), `purchase_type` (repeatable), `responsible`, `region` (repeatable, 2-digit code), `published_from`, `published_to`, `price_min`, `price_max`, `has_location`, `loc_key`.

## How the prediction pipeline is wired

```
GET /fz44/purchases/{n}  ──►  app/services/mapper.build_raw()  ──►  raw dict (RAW_COLS)
        top-level fields only                                              │
        (never docs, never /protocols)                                     ▼
                                                  app/ml/predictor.raw_to_frame()   (dtypes, UTC datetimes)
                                                                            │
                          app/ml/pipeline.ModelBundle.build_X()  ◄──────────┘
                            add_codes() → base_features() → TF-IDF text scores
                            → history_features() (indexes rebuilt from store.parquet)
                            → select config["features"] in order
                                                                            │
                          clf / reg / l2 → mix_median()  ────────────────►  predicted_price (one contract)
                                                                            predicted_price_for_sums (totals)
```

* `app/ml/pipeline.py` is a **faithful copy** of the notebook functions (cells 0, 2, 4): same logic and order, with only notebook globals turned into explicit parameters / attributes. `tests/test_pipeline_parity.py` executes the notebook's own function definitions (extracted by `ast` from `tests/fixtures/model_train.ipynb`) and asserts identical features and predictions, plus reference numbers from a notebook run on the real artifact.
* The model folder is loaded **once**, in a background thread; history indexes (`build_all_indexes`) are rebuilt from `store.parquet` (≈ 20 s) and the 2.87 M-row store is then released.
* Inference is serialized with a lock; uploads predict in one vectorised batch.
* Output: `predicted_price`, `predicted_price_for_sums`, `ratio_median/mean`, expected discount vs. `max_price`, `p_low` / `p_partial` / `p_nodrop` (outcome probabilities), history depth (`organizer_n`, `group2_n`, `group5_n`) and human-readable warnings. The model has **no confidence interval**; the UI shows the README's typical error (≈ 15 % of `max_price`, ≈ 3 % for EZT) as a reference value only.
* A tender that cannot be predicted (unsupported type such as EOK, missing/≤1 `max_price`, missing `published_at`, model not loaded) is stored and listed with a readable reason; it never crashes a batch.

### Deliberate differences from the task text (both change predictions or avoid crashes)

1. **Null `object_info` stays null.** The task mapping says `object_info or ""`. Training data had 319,210 nulls and **zero** empty strings, and `txt_len = object_info.str.len()` is `NaN` for a null but `0` for `""`. On the sample tender the median ratio is 0.92 with a null vs 0.90 with `""`. The pipeline's own `fillna("")` is still applied for the TF-IDF part, exactly as in the notebook.
2. **Missing organizer (`responsible`)** is passed as the notebook's own `"__NA__"` sentinel. Under pandas 3 the notebook's `make_keys` raises on a null (training data never had one); the sentinel gives the intended "no organizer history → global prior" path. Covered by a test.

## Winner price (display only)

`app/services/winner.py`. After upload the service calls `/protocols`; the winner is the application with the **lowest numeric `appRating`** and `winner_price = float(finalPrice)`. Priority: EZK final → EF final (`finalPrice`, then `lastPriceOffer.price`) → EZT final → EF submit-offers (`priceOffer.price`, flagged *preliminary*). Newest protocol version first. Valid only if `0 < price <= max_price`, otherwise treated as missing and not shown. An uploaded record's top-level `winner_price` is validated the same way. It never reaches the model.

**Verified** on a real record: the EZK final protocol path and the `appRating` rule (147,150 vs 901,989 → 147,150). **Not verified** (not present in the notebook, which reads a pre-built table; no live access to these records): the EF and EZT paths and EZT's final-price field. They follow the task text and are easy to adjust in `PRICE_PATHS`.

## Location data

A real GosPlan response contains **no coordinates**. It has an integer top-level `region` (e.g. `25` = Primorsky Krai, consistent with the delivery address), empty `delivery_places` / `delivery_places_kladr` arrays, and free-text addresses nested in `docs[*]`. So points are placed at the **centre of the region** from a bundled table (`app/data/regions.json`, built from Natural Earth by `scripts/build_geo_data.py`) and marked **Approximate location** in the UI. If a record ever carries `latitude/longitude` (top level or inside `delivery_places`), those exact coordinates are used instead. Tenders without a resolvable region are still stored, searchable and filterable, but not drawn (counted as "not on map").

Region codes are the two-digit FIAS/GAR subject codes; only `25 ↔ Primorsky` was verified against real data. Codes missing from the table (e.g. newer territories) get no map point. Borders come from Natural Earth (public domain) and reflect that dataset's conventions; replace `app/static/data/*.geojson` and `app/data/regions.json` to use different boundaries.

## Development

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
PREDICTOR_ARTIFACT=artifacts/hf_model pytest               # 93 tests; the heavy `model` tests are skipped without the model folder,
                                                            # LEGACY_JOBLIB=/path/predictor.joblib additionally enables folder-vs-joblib equivalence
ruff check app tests
node --test tests/frontend_i18n.test.mjs                     # optional frontend language tests (Node.js, no npm install)
uvicorn app.main:app_factory --factory --reload             # uses ./artifacts/hf_model, ./data/tenders.db
```

Tests: feature order vs the model's `features`, parity with notebook code, RAW_COLS mapping, null/missing handling, winner extraction for every protocol type (incl. the `appRating` example) and validation rules, GosPlan client retries/backoff/timeouts with a mock transport, and all API endpoints with a mocked GosPlan client.

## Known limitations

* **Accuracy is limited by the notice.** Expect about 13–15 % of `max_price` average error per contract. Partial-drop auctions (EF, EZK) carry ~70 % of the error because bidder count and competition are unknown at notice time; per-unit contracts without a signal in the notice can be missed badly. The sample tender (predicted ₽699k, actual winner ₽147k) is such a case.
* The reported metrics were measured on April–May 2026, which also influenced design decisions, so they are slightly optimistic; there is no clean holdout.
* **History goes stale.** The artifact's store ends on 2026-06-02; tenders published later get a warning and do not benefit from newer organizer behaviour. The service does not append finished purchases to the store (the notebook's `update_store` is not ported), so retrain/refresh the artifact periodically.
* Data covers 2025-01 → 2026-05 only; seasonality and year-end effects cannot be separated from trend.
* Single worker by design (model and indexes in process memory, SQLite single writer). Memory: allow ≥ 3 GB.
* Timestamps from GosPlan are naive UTC and shown as UTC; the model treats `published_at` as UTC as in training.

## Project layout

```
app/
  main.py  config.py  logging_conf.py
  api/        tenders.py  meta.py  deps.py  schemas.py
  ml/         pipeline.py (notebook port)  predictor.py (service wrapper)  manifest.py (folder checks)
  services/   gosplan.py  mapper.py  winner.py  locations.py  db.py  tender_service.py  util.py
  data/       regions.json
  static/     index.html  css/  js/  vendor/maplibre-gl.*  fonts/  data/*.geojson
scripts/      build_geo_data.py  download_model.py
tests/        fixtures/ (real GosPlan record, notebook)  test_*.py
artifacts/    hf_model/ goes here (scripts/download_model.py)
```

Third-party assets: MapLibre GL JS 5.24.0 (BSD-3-Clause), IBM Plex Sans (SIL OFL 1.1), Natural Earth (public domain). Licenses are included next to the files.

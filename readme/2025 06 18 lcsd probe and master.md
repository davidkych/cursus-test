# Cursus ‣ Deployment & API Reference

This short README summarises **all changes introduced on 2025‑06‑18** – mainly the new *LCSD athletic‑field* features and the Unicode fix – so you can copy‑paste it into your repository.

---

## 1. Project structure (high‑level)

```
src/
  main.py                          # FastAPI bootstrap – includes routes listed below
  routers/
    jsondata/                      # Existing generic JSON upload/query module
    lcsd/
      probe_endpoints.py           # NEW – /api/lcsd/probe …
      html_probe_endpoints.py      # NEW – /api/lcsd/probe/html
      master_endpoints.py          # NEW – /api/lcsd/master …
      html_master_endpoints.py     # NEW – /api/lcsd/master/html
infra/
  main.bicep                       # unchanged – exposes COSMOS_ENDPOINT etc.
.github/workflows/deploy.yml       # unchanged – CI/CD pipeline
```

### New runtime dependencies

```
requests==2.32.3
beautifulsoup4==4.12.3
```

Both were appended to `src/requirements.txt` so the GitHub Action vendors them during deploy.

---

## 2. JSON router – Unicode patch

* **File:** `src/routers/jsondata/endpoints.py`
* **Change:** in `download_json_file()` the payload is now serialised with `ensure_ascii=False`:

```python
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
```

This prevents Chinese characters from being escaped as `\uXXXX` in downloaded attachments.

---

## 3. LCSD Athletic‑Field tooling

### 3.1 Probe endpoint (`/api/lcsd/probe`)

| Verb | Path                   | Purpose                          |
| ---- | ---------------------- | -------------------------------- |
| GET  | `/api/lcsd/probe`      | Probe DID range via query params |
| POST | `/api/lcsd/probe`      | Probe via JSON body              |
| GET  | `/api/lcsd/probe/html` | Simple HTML form in the browser  |

**Parameters** (query or JSON body)

| Name       | Type  | Default | Notes                      |
| ---------- | ----- | ------- | -------------------------- |
| `startDid` | int   | 0       | inclusive                  |
| `endDid`   | int   | 20      | inclusive, ≥ `startDid`    |
| `delay`    | float | 0.1     | seconds between HTTP calls |

On completion the endpoint:

1. Writes a probe file to `/tmp/…_lcsd_af_probe.json` (for inspection).
2. **Upserts** the same data into Cosmos with
   `tag="lcsd"`, `secondary_tag="probe"`, `year/month/day=<today>`.

#### Usage examples

```bash
# Browser (quick test)
https://cursus-app.azurewebsites.net/api/lcsd/probe?startDid=0&endDid=20

# cURL – JSON body
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"startDid":0,"endDid":20}' \
  https://cursus-app.azurewebsites.net/api/lcsd/probe
```

Retrieve probe data later:

```bash
curl "https://cursus-app.azurewebsites.net/api/json?tag=lcsd&secondary_tag=probe&year=2025&month=6&day=18"
```

### 3.2 Master builder (`/api/lcsd/master`)

| Verb | Path                    | Purpose                               |
| ---- | ----------------------- | ------------------------------------- |
| GET  | `/api/lcsd/master`      | Build master JSON from latest probe   |
| POST | `/api/lcsd/master`      | Same but JSON body `{ "delay": 0.2 }` |
| GET  | `/api/lcsd/master/html` | HTML trigger                          |

Behaviour:

1. Fetches the **most recent** probe doc via Cosmos SQL `ORDER BY c._ts DESC LIMIT 1`.
2. For every `valid_did` downloads the LCSD details page and parses each facility (BeautifulSoup).
3. Aggregates the output under `facilities[]`, stamps
   `metadata.timestamp` and `source="latest_probe"`.
4. Upserts into Cosmos with `tag="lcsd"`, `secondary_tag="master"`, `year/month/day=<today>`.

Example build + fetch:

```bash
# Run the builder (defaults OK)
curl https://cursus-app.azurewebsites.net/api/lcsd/master

# Retrieve consolidated JSON
year=`date +%Y`; month=`date +%-m`; day=`date +%-d`
curl "https://cursus-app.azurewebsites.net/api/json?tag=lcsd&secondary_tag=master&year=$year&month=$month&day=$day" |
  jq .metadata.count
```

---

## 4. Health & logs

During deployment Azure restarts the container and *Gunicorn* logs
`Worker ... was sent SIGTERM!` at level `ERROR`. **This is expected** – it simply
indicates a graceful shutdown before the new image is swapped in. The deploy
script’s own `/healthz` check confirms readiness.

---

## 5. Quick route map

```
Core
  /api/hello                – hello‐world JSON
  /healthz                  – liveness probe
  /api/json/*               – generic JSON upload / list / download

LCSD
  /api/lcsd/probe           – probe athletic‑field DID range (GET/POST)
  /api/lcsd/probe/html      – browser form
  /api/lcsd/master          – build consolidated master from newest probe
  /api/lcsd/master/html     – browser form
```

---

*Last updated : 2025‑06‑18*

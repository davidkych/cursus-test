# Change Summary

This document outlines the recent modifications and additions to the codebase.

---

## 1. JSON Data Endpoint: Pretty‑Printed Download

* **File modified**: `src/routers/jsondata/endpoints.py`
* **Endpoint**: `/api/json/download`
* **Change**: JSON payload is now serialized with `indent=2` and `ensure_ascii=False` for human‑readable formatting.
* **Usage**: Download the JSON file via:

  ```bash
  curl -O "https://cursus-app.azurewebsites.net/api/json/download?tag=<TAG>&secondary_tag=<SEC>&year=<YYYY>&month=<MM>&day=<DD>"
  ```

---

## 2. New LCSD Timetable‑Probe API

### Backend

* **New file**: `src/routers/lcsd/timetableprobe_endpoints.py`
* **Routes**:

  * `GET  /api/lcsd/timetableprobe?delay=<seconds>`
  * `POST /api/lcsd/timetableprobe` with JSON body `{ "delay": <seconds> }`
* **Behavior**:

  1. Fetches the **latest** probe JSON (`tag='lcsd'`, `secondary_tag='probe'`).
  2. For each `did` in `valid_dids`, retrieves facility page and extracts only:

     * `did_number`
     * `lcsd_number`
     * `name`
     * `jogging_schedule` (list of objects with `month_year`, `excel_url`, `pdf_url`)
  3. Stores consolidated JSON under `tag='lcsd'`, `secondary_tag='timetableprobe'`, dated **today**.

### Browser Form

* **New file**: `src/routers/lcsd/html_timetableprobe_endpoints.py`
* **Form URL**: `/api/lcsd/timetableprobe/html`
* **Launch**: Open in browser to specify `delay` and trigger the probe via a simple HTML form.

### Integration

* **Main file update**: `src/main.py`

  * Added imports and `app.include_router(...)` for both the `/api/lcsd/timetableprobe` and `/api/lcsd/timetableprobe/html` routers.

---

## 3. How to Launch

### Via HTTP prompt (cURL)

```bash
# GET with default delay (0.1s)
curl -X GET "https://cursus-app.azurewebsites.net/api/lcsd/timetableprobe"

# POST with custom delay
echo '{"delay":0.2}' \
  | curl -X POST -H 'Content-Type: application/json' \
    -d @- "https://cursus-app.azurewebsites.net/api/lcsd/timetableprobe"
```

### Via Weblink (browser)

* **HTML form**: `https://cursus-app.azurewebsites.net/api/lcsd/timetableprobe/html`
* Select your desired **Delay** and click **Run timetable‑probe**.

---

*For detailed code, see the corresponding files in `src/routers/jsondata` and `src/routers/lcsd`.*

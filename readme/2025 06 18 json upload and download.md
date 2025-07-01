# JSON Data Module README

This module provides a simple FastAPI-based interface to upload, store, retrieve, download, list, and delete arbitrary JSON documents in Azure Cosmos DB. It supports JSON-body and form-based uploads, browser-friendly download and delete links, and an HTML table listing all items.

---

## Prerequisites

* **Python 3.9+**
* **FastAPI**, **uvicorn**
* **Azure Cosmos DB** account (SQL API)
* Environment variables set:

  * `COSMOS_ENDPOINT` – your Cosmos DB endpoint URL
  * `COSMOS_DATABASE` – name of the database (default: `cursusdb`)
  * `COSMOS_CONTAINER` – name of the container (default: `jsonContainer`)
  * `COSMOS_KEY` – *optional* key if not using managed identity

---

## Base URL

All endpoints are rooted at:

```
https://cursus-app.azurewebsites.net
```

---

## Endpoints and Usage

### 1. Upload JSON (raw body)

* **URL**: `POST /api/json`
* **Full URL**: `https://cursus-app.azurewebsites.net/api/json`
* **Request Body** (JSON):

  ```jsonc
  {
    "tag": "mytag",
    "secondary_tag": "subtag",   // optional
    "year": 2025,                  // optional
    "month": 6,                    // optional
    "day": 3,                      // optional
    "data": { /* any JSON object or array */ }
  }
  ```
* **Response**:

  ```json
  {"status":"success","id":"mytag_subtag_2025_6_3"}
  ```

**cURL example**:

```bash
curl -X POST "https://cursus-app.azurewebsites.net/api/json" \
     -H "Content-Type: application/json" \
     -d @payload.json
```

**PowerShell**:

```powershell
Invoke-RestMethod -Uri "https://cursus-app.azurewebsites.net/api/json" `
                  -Method Post `
                  -ContentType "application/json" `
                  -InFile "C:\path\to\payload.json"
```

---

### 2. Download JSON (inline)

* **URL**: `GET /api/json`
* **Full URL**: `https://cursus-app.azurewebsites.net/api/json`
* **Query parameters**:

  * `tag` (required)
  * `secondary_tag` (optional)
  * `year`, `month`, `day` (optional)

**Example**:

```
https://cursus-app.azurewebsites.net/api/json?tag=lcsd&year=2025&month=6
```

---

### 3. Download JSON as attachment

* **URL**: `GET /api/json/download`
* **Full URL**: `https://cursus-app.azurewebsites.net/api/json/download`
* Returns `Content-Disposition: attachment` so browser prompts to save.

**Browser link example**:

```
https://cursus-app.azurewebsites.net/api/json/download?tag=lcsd&year=2025&month=6
```

**PowerShell**:

```powershell
Invoke-WebRequest -Uri "https://cursus-app.azurewebsites.net/api/json/download?tag=lcsd&year=2025&month=6" `
                  -OutFile "C:\temp\lcsd_2025_06.json"
```

---

### 4. Delete JSON item

* **URL**: `GET /api/json/delete`
* **Full URL**: `https://cursus-app.azurewebsites.net/api/json/delete`
* Deletes the specified item and returns status.

**Browser link example**:

```
https://cursus-app.azurewebsites.net/api/json/delete?tag=lcsd&year=2025&month=6
```

---

### 5. HTML form upload

* **URL**: `GET /api/json/upload`
* **Full URL**: `https://cursus-app.azurewebsites.net/api/json/upload`
* Presents a simple browser form for manual metadata entry and file selection.
* **Action**: `POST /api/json/upload`

Access the form:

```
https://cursus-app.azurewebsites.net/api/json/upload
```

---

### 6. List all JSON items (HTML table)

* **URL**: `GET /api/json/list`
* **Full URL**: `https://cursus-app.azurewebsites.net/api/json/list`
* Renders an HTML page with a table of all items (tag, secondary\_tag, year, month, day) and **Download** / **Delete** links per row.

Access the listing:

```
https://cursus-app.azurewebsites.net/api/json/list
```

---

## Summary of Endpoints

| Method | Path                 | Purpose              |
| ------ | -------------------- | -------------------- |
| POST   | `/api/json`          | JSON-body upload     |
| GET    | `/api/json`          | Inline JSON download |
| GET    | `/api/json/download` | Attachment download  |
| GET    | `/api/json/delete`   | Delete item          |
| GET    | `/api/json/upload`   | HTML upload form     |
| POST   | `/api/json/upload`   | Form upload handler  |
| GET    | `/api/json/list`     | HTML table listing   |

---

*Copy and paste this README into your project’s `README.md` to guide users through the JSON module features.*

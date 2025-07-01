# ── src/routers/log/html_console_endpoint.py ─────────────────────────
"""
Browser-friendly console for viewing log records stored in Cosmos-DB.

•  /api/log/console/                → list all existing log documents
•  /api/log/console/<log_id>        → table view of one specific log
"""
from typing import List, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
import os, html

# ── Router -------------------------------------------------------------
router = APIRouter()

# ── Cosmos setup (share the same ENV variables as other modules) ------
_cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
_database_name   = os.getenv("COSMOS_DATABASE",  "cursusdb")
_container_name  = os.getenv("COSMOS_CONTAINER", "jsonContainer")
_cosmos_key      = os.getenv("COSMOS_KEY")

if _cosmos_key:
    _client = CosmosClient(_cosmos_endpoint, credential=_cosmos_key)
else:
    _client = CosmosClient(_cosmos_endpoint, credential=DefaultAzureCredential())

_database  = _client.get_database_client(_database_name)
_container = _database.get_container_client(_container_name)

# ── Helpers ------------------------------------------------------------
def _html_page(title: str, body: str) -> str:
    """Simple, dependency-free HTML template."""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
      body {{ font-family: Arial, sans-serif; margin: 2rem; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ccc; padding: .45rem .6rem; text-align: left; }}
      th {{ background: #f2f2f2; }}
      a.button {{
          display: inline-block; padding: .3rem .7rem; margin: 0 .2rem;
          background: #0078d4; color: #fff; border-radius: 4px; text-decoration: none;
      }}
      a.button:hover {{ background: #005a9e; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""

def _query_logs() -> List[Dict]:
    """
    Fetch all log documents (single partition “log”).
    We sort client-side to avoid composite-index requirements.
    """
    query = """
        SELECT
            c.id,
            c.secondary_tag,
            c.tertiary_tag,
            c.year, c.month, c.day,
            ARRAY_LENGTH(c.data) AS entries
        FROM   c
        WHERE  c.tag = @tag
    """
    params = [ { "name": "@tag", "value": "log" } ]
    try:
        items = list(_container.query_items(
            query=query,
            parameters=params,
            partition_key="log"
        ))
    except exceptions.CosmosHttpResponseError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cosmos query failed: {exc.message}"
        ) from exc

    # ── newest first (year-month-day) ────────────────────────────────
    items.sort(key=lambda r: (r.get("year", 0),
                              r.get("month", 0),
                              r.get("day", 0)),
               reverse=True)
    return items

# ── Routes -------------------------------------------------------------
@router.get("/api/log/console/", include_in_schema=False,
            response_class=HTMLResponse)
def list_log_documents():
    """Render a table listing every saved log document."""
    records = _query_logs()

    if not records:
        body = "<h2>No logs found</h2>"
        return _html_page("Log Console – no logs", body)

    rows = []
    for r in records:
        log_id         = html.escape(r["id"])
        secondary_tag  = html.escape(r.get("secondary_tag") or "")
        tertiary_tag   = html.escape(r.get("tertiary_tag")  or "")
        y, m, d        = r["year"], r["month"], r["day"]
        entries        = r["entries"]

        rows.append(f"""
        <tr>
            <td>{log_id}</td>
            <td>{secondary_tag}</td>
            <td>{tertiary_tag}</td>
            <td>{y:04d}-{m:02d}-{d:02d}</td>
            <td>{entries}</td>
            <td>
                <a class="button" href="/api/log/console/{log_id}">View</a>
            </td>
        </tr>""")

    body = f"""
    <h2>Log Documents</h2>
    <table>
        <thead>
            <tr>
                <th>Log ID</th>
                <th>Secondary tag</th>
                <th>Tertiary tag</th>
                <th>Date</th>
                <th>Entries</th>
                <th></th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """
    return _html_page("Log Console", body)

@router.get("/api/log/console/{log_id}", include_in_schema=False,
            response_class=HTMLResponse)
def view_log_document(log_id: str):
    """Display one specific log (each entry in its own table row)."""
    try:
        item = _container.read_item(item=log_id, partition_key="log")
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Log not found")

    entries = item.get("data", [])
    if not entries:
        body = f"<p>No entries in log <code>{html.escape(log_id)}</code>.</p>"
        return _html_page(f"Log {log_id}", body)

    rows = []
    for e in entries:
        ts   = html.escape(e.get("timestamp", ""))
        base = html.escape(e.get("base", ""))
        msg  = html.escape(e.get("message", ""))
        sec  = html.escape(e.get("secondary_tag", ""))
        ter  = html.escape(e.get("tertiary_tag", ""))
        rows.append(f"""
        <tr>
            <td>{ts}</td>
            <td>{base}</td>
            <td>{msg}</td>
            <td>{sec}</td>
            <td>{ter}</td>
        </tr>""")

    body = f"""
    <a class="button" href="/api/log/console/">← Back</a>
    <h2>Log <code>{html.escape(log_id)}</code></h2>
    <table>
        <thead>
            <tr>
                <th>Timestamp (HKT)</th>
                <th>Level</th>
                <th>Message</th>
                <th>Secondary tag</th>
                <th>Tertiary tag</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """
    return _html_page(f"Log {log_id}", body)

# ── src/routers/lcsd/lcsd_af_adminupload_timetable_layout.py ────────────────
"""
Pure-layout module for the *Admin Upload Timetable* page.

Separated from the route/logic file to keep HTML away from backend code.
"""

UPLOAD_FORM_HTML: str = """
<!doctype html>
<html>
<head><title>LCSD — Admin Upload Timetable JSON</title></head>
<body>
  <h2>LCSD ‧ Admin Upload of Timetable JSON</h2>
  <p>
    Select a <code>.json</code> file exported by the Excel-parser tool and
    click <strong>Upload</strong>.  
    The backend will:
  </p>
  <ol>
    <li>Convert it into the master <em>af_availtimetable</em> document,</li>
    <li>Split the file into per-facility <em>af_excel_timetable</em> records,</li>
    <li>Save everything to Cosmos DB.</li>
  </ol>

  <form action="/api/lcsd/lcsd_af_adminupload_timetable/upload"
        method="post" enctype="multipart/form-data">
    <label>Select JSON:&nbsp;
      <input type="file" name="file" accept=".json" required>
    </label>
    &nbsp;&nbsp;
    <button type="submit">Upload</button>
  </form>
</body>
</html>
"""

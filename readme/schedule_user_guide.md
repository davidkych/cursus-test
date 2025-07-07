## Usage Guide: Scheduling Function API

This guide summarizes all the ways you can interact with the Schedule Function in the `cursus-test` application. It covers available endpoints, payloads, behaviors, and supported prompt types.

---

### 1. Create a Scheduled Job

**Endpoint**: `POST /api/schedule`

**Description**: Schedule a one-off task to run at a specified future time.

**Request Body (`ScheduleRequest`)**:

```json
{
  "exec_at": "<ISO-8601 datetime with offset>",
  "prompt_type": "<prompt_type>",
  "payload": { ... }
}
```

* `exec_at`: ISO-8601 timestamp with offset (e.g. `2025-07-07T16:00:00+08:00`). Must be at least 60 seconds in the future.
* `prompt_type`: Specifies the handler to invoke. Supported types:

  * `log.append`: Append a structured log to the FastAPI `/api/log` endpoint.
  * `http.call`: Perform an arbitrary HTTP request (configurable method, headers, body, timeout).
* `payload`: Handler-specific JSON payload:

  * For `log.append`: `{ "tag": "<secondary_tag>", "base": "<level>", "message": "<text>" }`
  * For `http.call`: `{ "url": "<url>", "method": "POST", "headers": {...}, "body": {...}, "timeout": 10 }`

**Response (`ScheduleResponse`)**:

```json
{ "transaction_id": "<instanceId>" }
```

**Notes**:

* Returns HTTP 202 Accepted on success, with `Location` header for status polling.
* Cold-start of the Function App is handled automatically by retries.

---

### 2. List All Scheduled Jobs

**Endpoint**: `GET /api/schedule`

**Description**: Retrieve a list of all pending and active scheduled jobs.

**Response**:

```json
{
  "jobs": [
    {
      "instanceId": "<id>",
      "exec_at_utc": "<UTC timestamp>",
      "prompt_type": "<type>",
      "runtimeStatus": "<status>"
    },
    ...
  ]
}
```

* `runtimeStatus`: One of `Pending`, `Running`, `Completed`, `Failed`, etc.

---

### 3. Fetch Schedule Status

**Endpoint**: `GET /api/schedule/{transaction_id}/status`

**Description**: Get detailed status and history of a specific orchestration instance.

**Response**: Full Durable Functions status JSON, including:

* Orchestration input & output
* History of events (timer created, activity invoked)
* Current `runtimeStatus`

---

### 4. Delete (Terminate) a Pending Job

**Endpoint**: `DELETE /api/schedule/{transaction_id}`

**Description**: Cancel and purge a pending job before it executes.

**Behavior**:

1. Terminates the orchestration instance.
2. Purges its history.
3. Removes from entity registry.

**Response**: HTTP 204 No Content on success, or 404 if not found/already completed.

---

### 5. Wipe All Schedules

**Endpoint**: `DELETE /api/schedule`

**Description**: Cancel, purge, and clear the registry of **all** scheduled jobs.

**Behavior**:

1. Iterates through all registry entries.
2. Terminates & purges each orchestration.
3. Resets the registry entity.

**Response**:

```json
{
  "terminated": ["<id1>", "<id2>", ...],
  "total": <number>
}
```

---

### 6. Prompt Types & Payloads

| Prompt Type  | Purpose                       | Required Payload Fields                           |
| ------------ | ----------------------------- | ------------------------------------------------- |
| `log.append` | Append structured log entries | `tag`, `base`, `message`                          |
| `http.call`  | Send arbitrary HTTP requests  | `url` (★), `method`, `headers`, `body`, `timeout` |

★ = required.

---

### 7. Health Check

**Endpoint**: `GET /healthz`

**Description**: Verify that the FastAPI app is running (includes scheduler health via `GET /api/healthz` on Function App).

**Response**:

```json
{ "status": "ok" }
```

---

### Usage Examples

* **Log a message at 3 PM HKT tomorrow**:

  ```bash
  curl -X POST https://.../api/schedule \
    -d '{"exec_at":"2025-07-08T15:00:00+08:00","prompt_type":"log.append","payload":{"tag":"daily","base":"info","message":"Daily run"}}'
  ```

* **Call an external API in 5 minutes**:

  ```bash
  TIME="$(date -u -d '+5 minutes' +%Y-%m-%dT%H:%M:%SZ)"
  curl -X POST https://.../api/schedule \
    -d '{"exec_at":"'$TIME'+00:00","prompt_type":"http.call","payload":{"url":"https://api.example.com/endpoint","method":"POST","headers":{},"body":{"key":"value"}}}'
  ```

Use these endpoints to automate logs, HTTP calls, or any custom prompt handler you implement in the Durable Functions app.

## Scheduled Job Lifecycle

This document traces the complete lifecycle of a scheduled job in the `cursus-test` application, from initial API call through execution to eventual disposal (completion, deletion, and full wipe).

---

### Table of Contents

1. [API Request](#api-request)
2. [Schedule Starter](#schedule-starter)
3. [Orchestration](#orchestration)
4. [Activity Execution](#activity-execution)
5. [Post-Execution Cleanup](#post-execution-cleanup)
6. [Status Queries](#status-queries)
7. [Deletion of a Pending Job](#deletion-of-a-pending-job)
8. [Wipe All Schedules](#wipe-all-schedules)
9. [Entity Registry Structure](#entity-registry-structure)

---

## API Request

1. **Client** sends `POST /api/schedule` to FastAPI

   * Payload:

     ```json
     {
       "exec_at": "2025-07-07T15:00:00+08:00",
       "prompt_type": "log.append",
       "payload": { "message": "Hello" }
     }
     ```
2. **FastAPI** validates using `ScheduleRequest` Pydantic model
3. FastAPI calls `schedule_starter` function endpoint with JSON body

---

## Schedule Starter

* **Function**: `schedule_starter/__init__.py`
* **Responsibilities**:

  1. Parse body and ensure `exec_at` is ISO-8601
  2. Convert to UTC-aware ISO via `utils.to_utc_iso`
  3. Start new orchestration: `client.start_new("schedule_orchestrator", None, input)`
  4. Signal entity registry to `add` job metadata
  5. Return `202 Accepted` with `Location` header pointing to status URL

---

## Orchestration

* **Function**: `schedule_orchestrator/__init__.py`
* **Steps**:

  1. **Register**: Signal `schedule_entity` to `add`:

     ```json
     {"instanceId":"<id>","exec_at_utc":"<UTC>+00:00","prompt_type":"log.append"}
     ```
  2. **Parse exec\_at** into a UTC `datetime`
  3. Compare with `ctx.current_utc_datetime` to compute `fire_at`
  4. **Wait** for `fire_at` via `ctx.create_timer(fire_at)`
  5. After timer, **invoke** `execute_prompt` activity
  6. Upon activity return, **signal** entity registry to `remove`
  7. **Return** activity result to caller

---

## Activity Execution

* **Function**: `execute_prompt/__init__.py`
* **Payload**: same `prompt_type` and `payload`
* **Handlers**:

  * `log.append` → proxy to FastAPI log endpoint
  * `http.call` → generic HTTP request
* **Error Handling**: all exceptions caught and logged; activity always completes

---

## Post-Execution Cleanup

1. Orchestrator signals `schedule_entity` to `remove` instanceId
2. Registry no longer lists completed job
3. Orchestration instance transitions to **Completed** status

---

## Status Queries

* **Endpoint**: `GET /api/schedule/{transaction_id}/status`

  * FastAPI forwards to Durable status (`status` function)
  * Returns JSON with `runtimeStatus` and history (if requested)

---

## Deletion of a Pending Job

1. **Client** calls `DELETE /api/schedule/{transaction_id}`
2. FastAPI `handle_delete` constructs terminate URL
3. **Function**: `terminate_instance` HTTP POST `/api/terminate/{instanceId}`

   * Internally: `client.terminate` and `client.purge_instance_history`
   * Signals entity to `remove`
4. Returns `204 No Content`
5. Job removed from registry and orchestration stopped

---

## Wipe All Schedules

1. **Client** calls `DELETE /api/schedule` (wipe)
2. FastAPI forwards to `/api/wipe` on function app
3. **Function**: `wipe_schedules` iterates all registry entries

   * Terminates & purges each instance
   * Calls entity `reset` to clear registry state
4. Returns JSON: `{"terminated": [...], "total": N}`

---

## Entity Registry Structure

The `schedule_entity` stores state as a map:

```json
{
  "<instanceId>": { "exec_at_utc": "...", "prompt_type": "..." },
  "<instanceId2>": { ... }
}
```

* **add**: add or overwrite entry
* **remove**: delete entry by key
* **reset**: clear map entirely

---

*End of lifecycle description.*

## Schedule Function Overview

This document provides a detailed description of the **Schedule Function** in the `cursus-test` application, covering both the FastAPI API façade and the Azure Functions-based Durable Scheduler Function App.

---

### Table of Contents

1. [Introduction](#introduction)
2. [API Side (FastAPI)](#api-side-fastapi)

   * [Routers & Endpoints](#routers--endpoints)
   * [Pydantic Models](#pydantic-models)
   * [Request Flow](#request-flow)
3. [Functional App Side (Durable Functions)](#functional-app-side-durable-functions)

   * [Architecture & Components](#architecture--components)
   * [Schedule Starter (`schedule_starter`)](#schedule-starter-schedule_starter)
   * [Orchestrator (`schedule_orchestrator`)](#orchestrator-schedule_orchestrator)
   * [Entity (`schedule_entity`)](#entity-schedule_entity)
   * [Activity (`execute_prompt`)](#activity-execute_prompt)
   * [Supporting Endpoints](#supporting-endpoints)

     * [Health Check (`healthz`)](#health-check-healthz)
     * [List Schedules (`list_schedules`)](#list-schedules-list_schedules)
     * [Status (`status`)](#status-status)
     * [Terminate Instance (`terminate_instance`)](#terminate-instance-terminate_instance)
     * [Wipe Schedules (`wipe_schedules`)](#wipe-schedules-wipe_schedules)
   * [Utility Functions (`utils.py`)](#utility-functions-utilspy)
4. [Deployment & Configuration](#deployment--configuration)
5. [Appendix: File Structure](#appendix-file-structure)

---

## Introduction

The Schedule Function enables users to schedule arbitrary tasks ("prompts") to be executed at a specified time in the future. It is composed of two main parts:

* **API Side**: A FastAPI router that exposes endpoints under `/api/schedule`
* **Functional App Side**: An Azure Functions app built on Durable Functions, implementing the scheduling workflow

Together, they provide a robust, scalable scheduling service.

---

## API Side (FastAPI)

### Routers & Endpoints

The FastAPI router is defined in `src/routers/schedule/endpoints.py` and registers under:

```python
app.include_router(schedule_router)
# Exposes:
# POST   /api/schedule        → Create a new scheduled job
# GET    /api/schedule        → List all schedules
# GET    /api/schedule/{id}/status → Get status
# DELETE /api/schedule/{id}   → Terminate a job
# DELETE /api/schedule        → Wipe all schedules
```

Each route delegates to handler functions in:

* `create_schedule` → `create.handle_create`
* `get_schedule_status` → `status.handle_status`
* `delete_schedule` → `delete.handle_delete`
* `list_schedules` → `list_schedules.handle_list`
* `wipe_schedules` → `wipe.handle_wipe`

### Pydantic Models

```python
class ScheduleRequest(BaseModel):
    exec_at:     str                # ISO-8601 with offset, ≥ 60s ahead
    prompt_type: str                # e.g. "log.append", "http.call"
    payload:     Dict[str, Any]

class ScheduleResponse(BaseModel):
    transaction_id: str
```

### Request Flow

1. **Validation**: Incoming JSON is validated against `ScheduleRequest`.
2. **Forwarding**: The request is forwarded to the Durable scheduler Function App (`schedule_starter`) via HTTP POST.
3. **Cold-Start Handling**: If 404 is returned (Function App cold), retries are attempted with backoff.
4. **Instance Extraction**: On success (202/200), the Durable Functions instance ID is returned.
5. **Response**: The FastAPI returns `{ "transaction_id": "<instanceId>" }` to the client.

Error handling and HTTPException wrapping ensure proper status codes.

---

## Functional App Side (Durable Functions)

### Architecture & Components

The Azure Functions app (`src/scheduler_fapp`) uses Durable Functions to implement:

* **Starter**: HTTP-triggered function that starts an orchestration
* **Orchestrator**: Coordinates waiting until the desired time, invokes the activity, and cleans up
* **Activity**: Executes the actual prompt (e.g. logging, HTTP call)
* **Entity**: Keeps a registry of pending jobs
* **Supporting HTTP Triggers**: Health check, list, status, terminate, wipe

### Schedule Starter (`schedule_starter`)

* **Trigger**: `POST /api/schedule`
* **File**: `schedule_starter/__init__.py`
* **Function.json**: Defines HTTP trigger and durableClient binding
* **Logic**:

  1. Parse & validate JSON keys (`exec_at`, `prompt_type`, `payload`)
  2. Normalize `exec_at` to UTC-aware ISO via `utils.to_utc_iso`
  3. Start orchestration `schedule_orchestrator` (awaited)
  4. Signal the registry entity to add the job
  5. Return `202 Accepted` with `Location` header pointing to durable status URL

### Orchestrator (`schedule_orchestrator`)

* **Trigger**: Durability orchestration
* **File**: `schedule_orchestrator/__init__.py`
* **Logic**:

  1. Signal `schedule_entity` to add with `{ instanceId, exec_at_utc, prompt_type }`
  2. Parse & compare `exec_at_utc` with current UTC (`ctx.current_utc_datetime`)
  3. Create timer to wait until `fire_at`
  4. On timer expiry, call `execute_prompt` activity
  5. Signal `schedule_entity` to remove job
  6. Return activity result

### Entity (`schedule_entity`)

* **Trigger**: `entityTrigger`
* **File**: `schedule_entity/__init__.py`
* **Operations**:

  * `add`: Add a job info to the registry
  * `remove`: Remove a job from registry
  * `reset`: Clear registry
  * `list`: (future) return registry state

### Activity (`execute_prompt`)

* **Trigger**: `activityTrigger`
* **File**: `execute_prompt/__init__.py`
* **Logic**:

  1. Dispatch to handler based on `prompt_type` (`log.append` or `http.call`)
  2. Fire-and-forget semantics: errors are caught and logged via `log_to_api`

### Supporting Endpoints

* **Health Check (`healthz`)**

  * Route: `GET /api/healthz`
  * Returns scheduler status, Python/runtime info, Durable extension loaded or not

* **List Schedules (`list_schedules`)**

  * Route: `GET /api/schedules`
  * Reads registry via Durable client, enriches with live `runtime_status`

* **Status (`status`)**

  * Route: `GET /api/status/{instanceId}`
  * Returns full Durable status with history and outputs

* **Terminate Instance (`terminate_instance`)**

  * Route: `POST /api/terminate/{instanceId}`
  * Terminates & purges instance, signals entity removal

* **Wipe Schedules (`wipe_schedules`)**

  * Route: `POST /api/wipe`
  * Terminates & purges all instances, resets registry

### Utility Functions (`utils.py`)

* `to_utc_iso(ts: str) -> str`: Normalize any ISO timestamp to UTC, enforce ≥60s lead
* `log_to_api(...)`: Post structured logs back to FastAPI `/api/log`
* Prompt handlers:

  * `_log_append`: Proxy to FastAPI log
  * `_http_call`: Generic HTTP caller supporting any method, headers, body

---

## Deployment & Configuration

* **Infrastructure**: Managed via Bicep files under `infra/`
* **Workflows**: GitHub Actions deploy both infra and functions via `azure/login`, `az deployment`, and ZIP packages
* **Environment Variables**:

  * `COSMOS_ENDPOINT`, `COSMOS_DATABASE`, `COSMOS_CONTAINER` for logs
  * `SCHEDULER_BASE_URL`, `SCHEDULER_MGMT_KEY` for scheduler URLs
  * `AzureWebJobsStorage` connection for Durable state

---

## Appendix: File Structure

```text
src/
└── routers/schedule/
    ├── create.py
    ├── delete.py
    ├── endpoints.py
    ├── helpers.py
    ├── list_schedules.py
    ├── status.py
    └── wipe.py

src/scheduler_fapp/
├── schedule_starter/      HTTP entry-point
├── schedule_orchestrator/ Durable orchestrator
├── schedule_entity/       Entity registry
├── execute_prompt/        Activity handler
├── healthz/               Health probe
├── list_schedules/        List jobs
├── status/                Durable status
├── terminate_instance/    Terminate helper
├── wipe_schedules/        Wipe-all helper
└── utils.py               Shared helpers
```

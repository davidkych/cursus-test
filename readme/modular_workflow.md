# Modular CI/CD Workflows & Targeted Deployment Triggers

This update refactors the single monolithic `deploy.yml` into two reusable workflows—**Scheduler** and **Web-App**—and adds both manual and path-based triggers so you can deploy only the piece you’ve changed.

---

## 📦 What Changed

1. **Split into Reusable Workflows**

   * **`web-app.yml`** handles FastAPI ZIP-deploy, health checks, restart, and Cosmos role assignment.
   * **`scheduler.yml`** handles Durable Function ZIP-deploy, health check, key retrieval, role assignment, and app-settings.

2. **Manual Dispatch**

   * Both workflows now include a `workflow_dispatch` trigger.
   * In GitHub Actions UI you can manually **Run workflow** to deploy only the Scheduler or only the Web-App.

3. **Path-Based Auto-Triggers**

   * **Scheduler** fires on pushes to `src/scheduler_fapp/**` only.
   * **Web-App** fires on pushes to `src/**` *excluding* `src/scheduler_fapp/**`.
   * This ensures you don’t rebuild and redeploy everything when only one module changes.

---

## 🔧 How to Trigger

### Scheduler-Only Deployment

* **Automatically** when you push to any file under `src/scheduler_fapp/…`
* **Manually** via **Actions → Scheduler Reusable → Run workflow**

#### Push Example

```bash
# Make a change to your durable-functions folder
git add src/scheduler_fapp/functions/healthz/__init__.py
git commit -m "Fix healthz route logic"
git push origin main
```

> As soon as GitHub receives this push, the **Scheduler** workflow will start, and **only** your scheduler code will be packaged and deployed.

---

### Web-App-Only Deployment

* **Automatically** when you push to any file under `src/…` *except* `src/scheduler_fapp/…`
* **Manually** via **Actions → Web-App Reusable → Run workflow**

#### Push Example

```bash
# Make a change to your FastAPI app
git add src/app/main.py
git commit -m "Add new /status endpoint"
git push origin main
```

> This triggers the **Web-App** workflow automatically, rebuilding and deploying just the FastAPI web app.

---

## Benefits

* **Speed:** Only the changed module runs, cutting build/deploy time.
* **Isolation:** Failures in one module won’t block the other.
* **Reusability:** Call these workflows from other pipelines (e.g. production) with different parameters.
* **Simplicity:** Clear separation of concerns—infra provisioning remains in its own reusable workflow.

---

## Next Steps

* Review any service-specific settings (timeouts, retry counts) per module.
* Optionally add a top-level “full deploy” workflow that calls **Infra**, **Web-App**, and **Scheduler** in sequence.
* Update team documentation or README to reference these new workflows and their triggers.

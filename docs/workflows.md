# Saved workspaces, batch predictions, and training progress

## Saved workspaces

In ML Studio, choose a target, features, preprocessing, and algorithms. Enter a workspace name and select **Save workspace**. Open **Projects → Saved analysis workspaces** to resume it.

A workspace stores ML settings, copies of that dataset's saved chart configurations, and the cleaning history of the saved dataset version. Save cleaning changes as a new dataset version before creating its ML workspace. Unsaved cleaning edits, prepared matrices, and fitted models are not included in a workspace; save models separately and prepare data again when resuming. Dataset deletion makes its workspaces unavailable.

Workspace records persist in the `analysis_workspaces` table. Startup creates the new table safely; migration `003_workspaces` also provides it for migration-managed installations. Every workspace operation checks account ownership.

## Predictions

Open **Saved Models → Predict new data**, upload a UTF-8 CSV, and download the original rows with a prediction column. Required feature names are shown on the page. Extra columns are retained, and existing prediction columns are not overwritten. Limits: 10 MB and 10,000 rows.

Inference uses the saved preprocessing and model; classification labels are decoded when the saved bundle includes label classes. Only server-created model files belonging to the current account are loaded. Old bundles without preprocessing need to be trained and saved again. Algorithms without `predict` cannot score new rows. CSV cells that could be interpreted as spreadsheet formulas are escaped.

## Training progress and cancellation

ML Studio reports the current model and the number completed. **Cancel training** is cooperative: a model already fitting finishes, then remaining models are skipped. The UI reconnects to its job after a refresh in the same tab. Job status and cancellation are scoped to both account and dataset. Resetting or changing configuration while a job is active is rejected.

Jobs and prepared data currently live in memory. A server restart interrupts jobs; completed-job status is retained for up to an hour until a later job prunes it. Durable workspaces and saved models survive restarts. Deploy with a single application worker and multiple threads (as configured in Docker); multiple workers require an external queue and shared workflow state. Cancellation currently applies to ML model comparison, not reports, time-series runs, or hyperparameter optimization.

## Verification

`tests/test_workflow_features.py` checks workspace persistence and ownership, repeated metadata loads, batch prediction values and column validation, safe CSV output, and cancellation ownership. The full suite and interactive preview cover existing routes and restored settings.

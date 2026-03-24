## Normal Processing Call Graph

- `app.py` stays the composition root: drains UI-visible events, reacts to user actions, and calls `app_runtime.py` only for Streamlit-facing worker lifecycle entrypoints.
- `app_runtime.py` is a thin adapter: it binds `state.py` session helpers to `processing_runtime.py` primitives for event draining, event application, and background worker start/stop.
- `processing_runtime.py` owns runtime event transport: background queue creation, `BackgroundRuntime`, typed event emit/apply helpers, worker lifecycle plumbing, upload markers, and restart/completed-source persistence transitions.
- `application_flow.py` owns preparation orchestration: upload resolution, synchronous/background preparation path, and `PreparedRunContext` assembly.
- `processing_service.py` owns worker dependency assembly only: it builds a singleton service and injects runtime-compatible emitters from `processing_runtime.py` into downstream processing collaborators.
- `document_pipeline.py` owns document processing orchestration after preparation: markdown generation, image processing callbacks, DOCX assembly, and runtime event emission through injected contracts.

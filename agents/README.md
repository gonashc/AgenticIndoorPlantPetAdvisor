# Recommendation agents

Engineer 2 owns the implemented Supervisor and selected-category specialist behavior. The current flow is deterministic and model-free; a versioned, constrained explanation prompt is ready for a future structured-output model adapter.

The eventual control flow is deterministic category routing → one specialist → evaluator → at most two targeted optimizer attempts → safe fallback or structured response.

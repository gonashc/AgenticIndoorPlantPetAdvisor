# Recommendation agents

The Supervisor and selected-category specialists keep eligibility, safety, and ranking deterministic.
A provider-neutral structured explanation stage is available behind a default-off configuration flag;
it is grounded only in approved retrieved passages and falls back to deterministic explanations.

The control flow is deterministic category routing → one specialist → approved retrieval → optional
structured explanation → evaluator → at most two targeted optimizer attempts → safe response.

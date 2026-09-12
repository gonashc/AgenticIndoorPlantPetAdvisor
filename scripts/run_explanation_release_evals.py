"""Evaluate one exact OpenAI explanation model and emit a deployment approval report."""

import argparse
import asyncio
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from advisor_api.config import Settings
from advisor_api.container import build_container
from advisor_api.contracts.base import VersionInfo
from advisor_api.observability import build_recommendation_tracer
from advisor_api.ports.generation import ExplanationGenerator

from agents.structured_generation import build_openai_explanation_adapter
from evaluations import (
    EXPLANATION_RELEASE_NAMESPACE,
    EXPLANATION_RELEASE_SUITE_VERSION,
    RECOMMENDATION_EVALUATORS,
    RecommendationEvaluationTarget,
    SyntheticApprovedKnowledgeRetriever,
    explanation_release_integrity,
    load_recommendation_dataset,
)


def _source_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


async def run(model: str, report_path: Path) -> bool:
    if re.fullmatch(r"[a-zA-Z0-9._-]+", model) is None:
        raise ValueError("Model must be an exact provider model identifier")
    settings = Settings()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise RuntimeError("OPENAI_API_KEY is required for the explanation release gate")
    generator = build_openai_explanation_adapter(
        api_key=settings.openai_api_key.get_secret_value(),
        model=model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    container = build_container(
        recommendation_tracer=build_recommendation_tracer(settings),
        knowledge_retriever=SyntheticApprovedKnowledgeRetriever(),
        explanation_generator=generator,
        enabled_categories=frozenset({"PLANT", "DOG", "CAT"}),
        knowledge_namespace=EXPLANATION_RELEASE_NAMESPACE,
    )
    target = RecommendationEvaluationTarget(container)
    try:
        return await _evaluate(model, report_path, generator, target)
    finally:
        container.close()


async def _evaluate(
    model: str,
    report_path: Path,
    generator: ExplanationGenerator,
    target: RecommendationEvaluationTarget,
) -> bool:
    prompt_version = generator.prompt_version
    model_version = generator.model_version
    dataset = load_recommendation_dataset()
    case_reports: list[dict[str, object]] = []
    all_passed = True
    for case in dataset.cases:
        outputs = await target(case.inputs)
        reference = case.reference_outputs.model_copy(deep=True)
        if reference.expected_status == "success":
            reference.expected_versions = VersionInfo(
                prompt=prompt_version,
                model=model_version,
                knowledge=EXPLANATION_RELEASE_NAMESPACE,
            )
        reference_data = reference.model_dump(mode="json")
        results = [evaluator(outputs, reference_data) for evaluator in RECOMMENDATION_EVALUATORS]
        results.append(
            explanation_release_integrity(
                outputs,
                expected_model=model,
                expected_prompt=prompt_version,
                expected_category=reference.expected_category,
            )
        )
        passed = all(result["score"] == 1 for result in results)
        all_passed = all_passed and passed
        case_reports.append(
            {
                "case_id": case.case_id,
                "passed": passed,
                "checks": results,
            }
        )
        print(f"{'PASS' if passed else 'FAIL'} {case.case_id}")

    report = {
        "contract_version": "v1",
        "approved": all_passed,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "source_commit": _source_commit(),
        "dataset_version": dataset.version,
        "suite_version": EXPLANATION_RELEASE_SUITE_VERSION,
        "prompt_version": prompt_version,
        "model": model,
        "knowledge_namespace": EXPLANATION_RELEASE_NAMESPACE,
        "cases": case_reports,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Approval report: {report_path}")
    return all_passed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Exact OpenAI model ID to evaluate.")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("explanation-release-report.json"),
        help="Path for the machine-readable approval report.",
    )
    args = parser.parse_args()
    return 0 if await run(args.model.strip(), args.report) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

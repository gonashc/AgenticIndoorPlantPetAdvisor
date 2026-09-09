"""Run the v1 recommendation baseline locally or as a LangSmith experiment."""

import argparse
import asyncio
from contextlib import AbstractContextManager, nullcontext
from uuid import NAMESPACE_URL, UUID, uuid5

from advisor_api.config import Settings
from advisor_api.container import build_container
from advisor_api.contracts.base import Category
from advisor_api.ports.observability import TraceTransport
from langsmith import Client, aevaluate

from evaluations import (
    RECOMMENDATION_EVALUATORS,
    RecommendationEvaluationTarget,
    load_recommendation_dataset,
)
from evaluations.recommendations import RecommendationEvaluationDataset


class InheritedRecommendationTracer:
    """Allows LangGraph nodes to inherit the LangSmith experiment trace."""

    def trace(
        self,
        *,
        request_id: UUID,
        category: Category,
        transport: TraceTransport,
    ) -> AbstractContextManager[None]:
        del request_id, category, transport
        return nullcontext()

    def close(self) -> None:
        return None


async def run_local(dataset: RecommendationEvaluationDataset) -> bool:
    target = RecommendationEvaluationTarget()
    passed = 0
    total = len(dataset.cases) * len(RECOMMENDATION_EVALUATORS)
    for case in dataset.cases:
        outputs = await target(case.inputs)
        references = case.reference_outputs.model_dump(mode="json")
        failures: list[str] = []
        for evaluator in RECOMMENDATION_EVALUATORS:
            result = evaluator(outputs, references)
            if result["score"] != 1:
                failures.append(f"{result['key']}: {result['comment']}")
            else:
                passed += 1
        status = "PASS" if not failures else "FAIL"
        print(f"{status} {case.case_id}")
        for failure in failures:
            print(f"  {failure}")
    print(f"Local evaluation score: {passed}/{total}")
    return passed == total


def sync_langsmith_dataset(client: Client, dataset: RecommendationEvaluationDataset) -> None:
    if client.has_dataset(dataset_name=dataset.name):
        remote_dataset = client.read_dataset(dataset_name=dataset.name)
    else:
        remote_dataset = client.create_dataset(
            dataset.name,
            description=dataset.description,
            metadata={"dataset_version": dataset.version, "data_classification": "synthetic"},
        )
    examples = [
        {
            "id": uuid5(NAMESPACE_URL, f"{dataset.name}:{case.case_id}"),
            "inputs": case.inputs,
            "outputs": case.reference_outputs.model_dump(mode="json"),
            "metadata": {
                **case.metadata,
                "case_id": case.case_id,
                "dataset_version": dataset.version,
                "data_classification": "synthetic",
            },
        }
        for case in dataset.cases
    ]
    existing_ids = {example.id for example in client.list_examples(dataset_id=remote_dataset.id)}
    updates = [example for example in examples if example["id"] in existing_ids]
    creates = [example for example in examples if example["id"] not in existing_ids]
    if updates:
        client.update_examples(dataset_id=remote_dataset.id, updates=updates)
    if creates:
        client.create_examples(dataset_id=remote_dataset.id, examples=creates)


async def run_langsmith(
    dataset: RecommendationEvaluationDataset,
    experiment_prefix: str,
) -> None:
    settings = Settings()
    if not settings.langsmith_tracing or settings.langsmith_api_key is None:
        raise RuntimeError("LangSmith tracing and API key are required for --upload")
    client = Client(
        api_url=settings.langsmith_endpoint,
        api_key=settings.langsmith_api_key.get_secret_value(),
        workspace_id=settings.langsmith_workspace_id,
        hide_inputs=settings.langsmith_hide_inputs,
        hide_outputs=settings.langsmith_hide_outputs,
    )
    try:
        sync_langsmith_dataset(client, dataset)
        target = RecommendationEvaluationTarget(
            build_container(recommendation_tracer=InheritedRecommendationTracer())
        )
        results = await aevaluate(
            target.__call__,
            data=dataset.name,
            evaluators=list(RECOMMENDATION_EVALUATORS),
            client=client,
            experiment_prefix=experiment_prefix,
            metadata={
                "dataset_version": dataset.version,
                "api_version": settings.api_version,
                "environment": settings.app_env,
            },
            max_concurrency=1,
        )
        await results.wait()
        print(f"LangSmith experiment: {results.experiment_name}")
        print(f"Results: {results.url}")
    finally:
        client.close(timeout=5.0)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Sync the synthetic dataset and publish an experiment to LangSmith.",
    )
    parser.add_argument(
        "--experiment-prefix",
        default="recommendation-v1-baseline",
        help="LangSmith experiment name prefix.",
    )
    args = parser.parse_args()
    dataset = load_recommendation_dataset()
    if not await run_local(dataset):
        return 1
    if args.upload:
        await run_langsmith(dataset, args.experiment_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

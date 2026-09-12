"""Export the deterministic OpenAPI artifact used by React client generation."""

import json
from pathlib import Path

from advisor_api import create_app
from advisor_api.config import Settings


def main() -> None:
    target = Path("packages/contracts/openapi/openapi.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            create_app(
                Settings(
                    _env_file=None,
                    app_env="test",
                    database_mode="memory",
                    auth_mode="disabled",
                    enabled_categories="PLANT,DOG,CAT",
                )
            ).openapi(),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

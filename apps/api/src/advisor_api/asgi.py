"""Environment-configured ASGI entrypoint for deployment."""

from advisor_api.application import create_app

app = create_app()

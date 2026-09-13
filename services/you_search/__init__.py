"""Shared bounded You.com Search API adapter."""

from services.you_search.client import YouSearchClient, YouSearchResult
from services.you_search.credentials import validate_you_api_key

__all__ = ["YouSearchClient", "YouSearchResult", "validate_you_api_key"]

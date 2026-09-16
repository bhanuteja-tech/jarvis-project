"""RapidAPI source package for job discovery."""

from app.sources.rapidapi.adapter import RapidApiAdapter
from app.sources.rapidapi.client import SOURCE_NAME, RapidApiClient

__all__ = [
    "SOURCE_NAME",
    "RapidApiClient",
    "RapidApiAdapter",
]

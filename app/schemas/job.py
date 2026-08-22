"""API-facing schemas.

The API layer consumes these rather than importing the domain module directly,
keeping transport concerns swappable. For now the canonical `Job` is exposed
verbatim; response shaping will evolve with later phases without touching the
domain model.
"""

from __future__ import annotations

from app.models.job import Job, Salary

__all__ = ["Job", "Salary"]

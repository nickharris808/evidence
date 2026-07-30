"""evidence — run the verification portfolio over your repository, and get ONE answer.

The aggregate is the WEAKEST leg, never the mean. Four checks that passed and one that could not
run is not "80% verified"; it is unverified, with four things known about it.
"""
__version__ = "0.1.1"

from .audit import audit, render                                    # noqa: E402
from .constituents import NOT_AUTOMATABLE, REGISTRY, Constituent    # noqa: E402
from .formats import to_junit, to_markdown, to_sarif                # noqa: E402
from .verdict import (FAILED, NOT_APPLICABLE, PASSED, UNAVAILABLE,  # noqa: E402
                      UNVERIFIED, Aggregate, LegResult, aggregate)

__all__ = ["audit", "render", "aggregate", "Aggregate", "LegResult", "Constituent", "REGISTRY",
           "NOT_AUTOMATABLE", "to_sarif", "to_junit", "to_markdown",
           "PASSED", "FAILED", "UNVERIFIED", "NOT_APPLICABLE", "UNAVAILABLE", "__version__"]

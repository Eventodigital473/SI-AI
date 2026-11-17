"""Retired legacy high-leverage planner.

SI-AI's active risk policy is fixed at 0.5% account risk, 20% maximum margin
allocation, and recommended 1x Futures leverage. This old 10%-risk/high-leverage
planner is intentionally disabled and must not be used by the active project.
"""
from __future__ import annotations


def build_paper_plan(**kwargs):
    """Reject all use of the retired high-leverage planner."""
    raise RuntimeError(
        "Legacy high-leverage planner is disabled. Use SI-AI's active "
        "0.5% risk / 20% margin allocation / 1x Futures policy."
    )

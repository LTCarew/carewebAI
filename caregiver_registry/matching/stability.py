"""
Stability Snapshot service for active caregiver–client relationships.

This module provides ``get_stability_snapshot(match)`` which returns a
deterministic, rule-based stability assessment for a single Match record.

Scoring strategy (Option A with Option B fallback):

  Option A — existing ScheduleEntryRating data (real experience signals)
    Ratings use a 1–10 scale across four shared metrics:
      care_fit_respect, communication_coordination,
      reliability_consistency, workload_support_balance

    Status thresholds (average across all ratings for this relationship):
      ≥ 7.5  → green  (Stable)
      ≥ 5.0  → yellow (Monitor)
      < 5.0  → red    (At Risk)

  Option B — match_score fallback when no ratings exist yet
    Uses the same 70 / 40 thresholds already displayed in _match_table.html
    so the UI is internally consistent:
      ≥ 70  → green
      ≥ 40  → yellow
      < 40  → red
    Explanation explicitly labels this as a demonstration estimate.

Results are deterministic across requests for the same data.
No AI API calls are made at render time.

Staff-only. Caller is responsible for org-scoping and permission checks.
"""

from django.db.models import Avg

# ── Thresholds ────────────────────────────────────────────────────────────────

# Option A: real rating averages (scale 1–10)
_RATING_GREEN  = 7.5
_RATING_YELLOW = 5.0

# Option B: match-score fallback (scale 0–100)
_SCORE_GREEN  = 70
_SCORE_YELLOW = 40


# ── Public interface ──────────────────────────────────────────────────────────

def get_stability_snapshot(match):
    """
    Return a stability snapshot dict for the given Match instance.

    Args:
        match: A ``matching.Match`` instance (must be pre-fetched or saveable).

    Returns a dict::

        {
            "status":  "green" | "yellow" | "red",
            "label":   "Stable" | "Monitor" | "At Risk",
            "score":   int (0–100, may be None when truly unknown),
            "source":  "ratings" | "match_score" | "neutral",
            "signals": {
                "schedule_consistency": "Good" | "Moderate" | "Poor",
                "travel_burden":        "Low"  | "Moderate" | "High",
                "access_alignment":     "Aligned" | "Partial mismatch" | "Significant mismatch",
                "care_continuity":      "Stable" | "Some disruption" | "Frequent disruption",
                "support_flags":        "None"   | "Follow-up suggested" | "Immediate review recommended",
            },
            "explanation": str,
            "review_requested": bool,
            "review_requested_by_name": str | None,
        }
    """
    from registry.models import ScheduleEntryRating

    # ── Pull all ratings linked to this specific match relationship ────────────
    # Ratings are connected via ScheduleEntry → Schedule → match FK.
    ratings_qs = ScheduleEntryRating.objects.filter(
        schedule_entry__schedule__match=match,
    )

    # ── Compute per-metric aggregates ─────────────────────────────────────────
    agg = ratings_qs.aggregate(
        avg_care_fit=Avg("care_fit_respect"),
        avg_communication=Avg("communication_coordination"),
        avg_reliability=Avg("reliability_consistency"),
        avg_workload=Avg("workload_support_balance"),
    )

    has_ratings = any(v is not None for v in agg.values())

    if has_ratings:
        avg_care_fit    = agg["avg_care_fit"]    or 0.0
        avg_reliability = agg["avg_reliability"] or 0.0
        avg_workload    = agg["avg_workload"]    or 0.0

        # Overall average (all four metrics combined)
        avg_overall = sum(
            v for v in agg.values() if v is not None
        ) / sum(1 for v in agg.values() if v is not None)

        status, label, score, explanation = _derive_from_ratings(
            avg_overall, avg_reliability, avg_care_fit, avg_workload, match
        )
        source = "ratings"
        signals = _signals_from_ratings(agg, avg_overall, match)

    else:
        # No ratings yet — fall back to match compatibility score
        status, label, score, explanation = _derive_from_score(match)
        source = "match_score" if match.match_score is not None else "neutral"
        signals = _signals_from_score(match)

    # Override support_flags if staff have already flagged this relationship
    if match.stabilization_review_requested:
        signals = dict(signals)
        signals["support_flags"] = "Immediate review recommended"

    reviewer_name = None
    if match.stabilization_review_requested and match.stabilization_review_requested_by:
        reviewer_name = match.stabilization_review_requested_by.display_name

    return {
        "status":  status,
        "label":   label,
        "score":   score,
        "source":  source,
        "signals": signals,
        "explanation": explanation,
        "review_requested": match.stabilization_review_requested,
        "review_requested_by_name": reviewer_name,
    }


# ── Private helpers: rating-based path ───────────────────────────────────────

def _derive_from_ratings(avg_overall, avg_reliability, avg_care_fit, avg_workload, match):
    """Classify status from real rating averages (1–10 scale)."""
    if avg_overall >= _RATING_GREEN:
        status = "green"
        label  = "Stable"
        score  = _rating_avg_to_score(avg_overall)
        explanation = (
            "This relationship appears stable. Session ratings are consistently strong, "
            "scheduling is reliable, and caregiver experience aligns with the client's needs."
        )
    elif avg_overall >= _RATING_YELLOW:
        status = "yellow"
        label  = "Monitor"
        score  = _rating_avg_to_score(avg_overall)
        explanation = (
            "This relationship has minor concerns. Session ratings are moderate — "
            "staff may want to check in to support consistency and communication."
        )
    else:
        status = "red"
        label  = "At Risk"
        score  = _rating_avg_to_score(avg_overall)
        explanation = (
            "This relationship may require support. Session ratings indicate repeated "
            "difficulties with scheduling, coordination, or care fit. "
            "Early intervention may help sustain the relationship."
        )
    return status, label, score, explanation


def _rating_avg_to_score(avg):
    """Map a 1–10 average to a 0–100 display score."""
    return round((avg / 10.0) * 100)


def _signals_from_ratings(agg, avg_overall, match):
    """Build the 5-signal dict from real aggregated rating metrics."""
    avg_reliability = agg["avg_reliability"] or 0.0
    avg_care_fit    = agg["avg_care_fit"]    or 0.0
    avg_workload    = agg["avg_workload"]    or 0.0

    # Schedule consistency ← reliability & consistency ratings
    if avg_reliability >= 7.5:
        schedule_consistency = "Good"
    elif avg_reliability >= 5.0:
        schedule_consistency = "Moderate"
    else:
        schedule_consistency = "Poor"

    # Travel burden ← real haversine distance stored in match_details
    travel_burden = _travel_burden_from_match(match)

    # Access alignment ← care fit & respect ratings
    if avg_care_fit >= 7.5:
        access_alignment = "Aligned"
    elif avg_care_fit >= 5.0:
        access_alignment = "Partial mismatch"
    else:
        access_alignment = "Significant mismatch"

    # Care continuity ← overall average
    if avg_overall >= 7.5:
        care_continuity = "Stable"
    elif avg_overall >= 5.0:
        care_continuity = "Some disruption"
    else:
        care_continuity = "Frequent disruption"

    # Support flags ← workload & support balance
    if avg_workload >= 7.5:
        support_flags = "None"
    elif avg_workload >= 5.0:
        support_flags = "Follow-up suggested"
    else:
        support_flags = "Immediate review recommended"

    return {
        "schedule_consistency": schedule_consistency,
        "travel_burden":        travel_burden,
        "access_alignment":     access_alignment,
        "care_continuity":      care_continuity,
        "support_flags":        support_flags,
    }


# ── Private helpers: match-score fallback path ────────────────────────────────

def _derive_from_score(match):
    """Classify status from compatibility score when no ratings exist yet."""
    ms = match.match_score

    if ms is None:
        status = "yellow"
        label  = "Monitor"
        score  = None
        explanation = (
            "No session ratings have been submitted yet for this relationship. "
            "This is a demonstration placeholder based on initial match data. "
            "Status will update automatically as ratings are submitted."
        )
    elif ms >= _SCORE_GREEN:
        status = "green"
        label  = "Stable"
        score  = round(ms)
        explanation = (
            "No session ratings have been submitted yet. "
            "This demonstration status is based on a strong initial match compatibility score "
            f"({round(ms)}/100) and placeholder stability rules. "
            "It will update as real session data becomes available."
        )
    elif ms >= _SCORE_YELLOW:
        status = "yellow"
        label  = "Monitor"
        score  = round(ms)
        explanation = (
            "No session ratings have been submitted yet. "
            "This demonstration status is based on a moderate initial match compatibility score "
            f"({round(ms)}/100) and placeholder stability rules. "
            "Staff may want to check in once sessions begin."
        )
    else:
        status = "red"
        label  = "At Risk"
        score  = round(ms)
        explanation = (
            "No session ratings have been submitted yet. "
            "This demonstration status is based on a lower initial match compatibility score "
            f"({round(ms)}/100) and placeholder stability rules. "
            "A follow-up conversation before sessions begin is recommended."
        )

    return status, label, score, explanation


def _signals_from_score(match):
    """Build signal labels when only the match_score and match_details are available."""
    ms      = match.match_score or 0.0
    details = match.match_details or {}

    # Schedule consistency — from availability overlap in match_details
    avail   = details.get("availability", {})
    avail_score = avail.get("score", 0.0)
    if avail_score >= 14.0:       # ≥ 70 % of 20-pt max
        schedule_consistency = "Good"
    elif avail_score >= 8.0:      # ≥ 40 % of 20-pt max
        schedule_consistency = "Moderate"
    else:
        schedule_consistency = "Poor"

    # Travel burden — from distance stored in match_details.location
    travel_burden = _travel_burden_from_match(match)

    # Access alignment — from tag/experience overlap score
    tag = details.get("tag_overlap", {})
    tag_score = tag.get("score", 0.0)
    if tag_score >= 28.0:         # ≥ 70 % of 40-pt max
        access_alignment = "Aligned"
    elif tag_score >= 16.0:       # ≥ 40 % of 40-pt max
        access_alignment = "Partial mismatch"
    else:
        access_alignment = "Significant mismatch"

    # Care continuity — from overall match score
    if ms >= _SCORE_GREEN:
        care_continuity = "Stable"
    elif ms >= _SCORE_YELLOW:
        care_continuity = "Some disruption"
    else:
        care_continuity = "Frequent disruption"

    # Support flags — neutral until sessions begin
    support_flags = "None"

    return {
        "schedule_consistency": schedule_consistency,
        "travel_burden":        travel_burden,
        "access_alignment":     access_alignment,
        "care_continuity":      care_continuity,
        "support_flags":        support_flags,
    }


# ── Shared helper ─────────────────────────────────────────────────────────────

def _travel_burden_from_match(match):
    """
    Derive travel burden label from the real haversine distance stored in
    match_details.location.distance_miles (computed at match-creation time).
    """
    details = match.match_details or {}
    location = details.get("location", {})
    dist = location.get("distance_miles")

    if dist is None:
        return "Moderate"   # unknown → cautious middle value
    if dist <= 5.0:
        return "Low"
    if dist <= 20.0:
        return "Moderate"
    return "High"

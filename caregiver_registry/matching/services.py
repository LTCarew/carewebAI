"""
Matching services: match creation, duplicate prevention, local scoring,
ChatGPT-assisted match generation, and notifications.
"""

import json
import logging

from django.conf import settings
from django.db import transaction

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]
    _OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)


# ==============================================
# Duplicate Prevention Helper
# ==============================================

def get_existing_active_or_pending_match(caregiver, client, organization):
    """
    Return any existing Match between caregiver and client in the same org
    that is active or pending, or None.
    """
    from .models import Match
    return Match.objects.filter(
        caregiver=caregiver,
        client=client,
        organization=organization,
        status__in=["pending", "active"],
    ).first()


# ==============================================
# Match Creation
# ==============================================

@transaction.atomic
def create_match(
    *,
    caregiver,
    client,
    organization,
    initiated_by,
    initiated_by_user,
    tag_ids=None,
    notes="",
    match_score=None,
    match_details=None,
    ai_reasoning="",
):
    """
    Create and return a new Match record.

    Raises ValueError if an active or pending match already exists between
    the caregiver and client in the same organization.

    Args:
        caregiver: CaregiverProfile instance
        client: ClientProfile instance
        organization: Organization instance
        initiated_by: str — 'caregiver', 'client', 'staff', or 'ai'
        initiated_by_user: UserProfile instance of the creator
        tag_ids: optional list of Tag PKs to associate
        notes: optional staff notes string
        match_score: optional float score
        match_details: optional dict with scoring breakdown
        ai_reasoning: optional string explanation

    Returns:
        Match instance
    """
    from .models import Match, Tag

    # Guard: prevent duplicate active/pending matches
    existing = get_existing_active_or_pending_match(caregiver, client, organization)
    if existing:
        raise ValueError(
            f"An active or pending match already exists between "
            f"{caregiver.user_profile.display_name} and {client.user_profile.display_name} "
            f"in {organization.name} (Match #{existing.pk})."
        )

    match = Match(
        organization=organization,
        caregiver=caregiver,
        client=client,
        initiated_by=initiated_by,
        initiated_by_user=initiated_by_user,
        notes=notes,
        match_score=match_score,
        match_details=match_details or {},
        ai_reasoning=ai_reasoning,
    )

    # Auto-approve the initiating party
    match.apply_initiator_status()
    match.save()

    # Associate tags
    if tag_ids:
        tags = Tag.objects.filter(pk__in=tag_ids, is_active=True)
        match.selected_tags.set(tags)

    # Fire notifications
    _notify_on_match_created(match)

    return match


# ==============================================
# Match Response Actions
# ==============================================

def caregiver_respond_to_match(match, action, user):
    """
    Caregiver approves or declines a match.

    Args:
        match: Match instance
        action: 'approve' or 'decline'
        user: User instance of the caregiver

    Raises PermissionError if user is not the caregiver on this match.
    """
    _verify_caregiver_ownership(match, user)
    if action == "approve":
        match.caregiver_approve()
        _notify_on_party_response(match, "caregiver", "approved")
    elif action == "decline":
        match.caregiver_decline()
        _notify_on_party_response(match, "caregiver", "declined")
    else:
        raise ValueError(f"Invalid action: {action!r}")


def client_respond_to_match(match, action, user):
    """
    Client approves or declines a match.

    Args:
        match: Match instance
        action: 'approve' or 'decline'
        user: User instance of the client

    Raises PermissionError if user is not the client on this match.
    """
    _verify_client_ownership(match, user)
    if action == "approve":
        match.client_approve()
        _notify_on_party_response(match, "client", "approved")
    elif action == "decline":
        match.client_decline()
        _notify_on_party_response(match, "client", "declined")
    else:
        raise ValueError(f"Invalid action: {action!r}")


def staff_respond_to_match(match, action, user):
    """
    Staff no longer approve or decline matches (two-party workflow).
    Raises PermissionError unconditionally.
    """
    raise PermissionError(
        "Staff do not approve or decline matches. "
        "Matches are approved by caregiver and client only."
    )


# ==============================================
# Ownership / Permission Checks
# ==============================================

def _verify_caregiver_ownership(match, user):
    """Raise PermissionError if user is not the caregiver on this match."""
    try:
        caregiver_profile = user.profile.caregiver_profile
        if match.caregiver != caregiver_profile:
            raise PermissionError(
                "You can only respond to match requests involving yourself."
            )
    except AttributeError:
        raise PermissionError("You do not have a caregiver profile.")


def _verify_client_ownership(match, user):
    """Raise PermissionError if user is not the client on this match."""
    try:
        client_profile = user.profile.client_profile
        if match.client != client_profile:
            raise PermissionError(
                "You can only respond to match requests involving yourself."
            )
    except AttributeError:
        raise PermissionError("You do not have a client profile.")


def _verify_staff_access(match, user):
    """Raise PermissionError if user is not staff/admin in the match's organization."""
    from registry.services import get_user_staff_role
    staff = get_user_staff_role(user, match.organization)
    if not staff:
        raise PermissionError(
            "You do not have staff access to this organization."
        )


# ==============================================
# Local AI Scoring (Stages 7 & 8)
# ==============================================

def compute_match_score(caregiver, client, selected_tag_ids=None):
    """
    Compute a compatibility score (0–100) and structured breakdown between
    a caregiver and client using local heuristics.

    Scoring factors and weights:
      - Tag overlap                  40 pts
      - Availability overlap         20 pts
      - Care needs / experience      20 pts
      - Location / ZIP match         10 pts
      - Transportation compatibility  5 pts
      - Language match                5 pts

    Args:
        caregiver: CaregiverProfile instance
        client: ClientProfile instance
        selected_tag_ids: optional list of Tag PKs explicitly selected

    Returns:
        dict with keys:
            score (float 0–100)
            details (dict with per-factor breakdown)
            ai_reasoning (str)
    """
    from .models import Tag

    details = {}
    total = 0.0

    # ── 1. Tag / experience overlap (40 pts) ────────────────────────────────
    caregiver_skills = set(caregiver.experience_with or [])
    client_needs = set(client.care_needs or [])
    tag_overlap = caregiver_skills & client_needs

    # Map experience_with keys to tag names (best-effort)
    if selected_tag_ids:
        selected_tags = list(
            Tag.objects.filter(pk__in=selected_tag_ids, is_active=True)
            .values_list("name", flat=True)
        )
    else:
        selected_tags = []

    # Score: number of overlapping needs / max possible, capped at 40
    if client_needs:
        tag_score = min(40.0, (len(tag_overlap) / len(client_needs)) * 40.0)
    else:
        tag_score = 20.0  # neutral if client has no listed needs
    details["tag_overlap"] = {
        "score": round(tag_score, 1),
        "overlapping": sorted(tag_overlap),
        "client_needs": sorted(client_needs),
        "caregiver_skills": sorted(caregiver_skills),
        "selected_tags": selected_tags,
    }
    total += tag_score

    # ── 2. Availability overlap (20 pts) ────────────────────────────────────
    # New format: {day: [period, ...]} e.g. {"monday": ["morning", "afternoon"]}
    caregiver_avail = caregiver.availability or {}
    client_avail = client.availability or {}

    # Build sets of (day, period) tuples
    caregiver_slots = set()
    for day, periods in caregiver_avail.items():
        if isinstance(periods, list):
            for p in periods:
                caregiver_slots.add((day, p))

    client_slots = set()
    for day, periods in client_avail.items():
        if isinstance(periods, list):
            for p in periods:
                client_slots.add((day, p))

    shared_slots = caregiver_slots & client_slots

    if caregiver_slots and client_slots:
        avail_score = min(20.0, (len(shared_slots) / max(len(client_slots), 1)) * 20.0)
    elif caregiver_avail and client_avail:
        # Both have availability but no period overlap
        avail_score = 0.0
    else:
        avail_score = 10.0  # neutral if either has no availability

    shared_days = sorted(set(day for day, _ in shared_slots))
    shared_slot_labels = sorted(f"{day} {period}" for day, period in shared_slots)

    details["availability"] = {
        "score": round(avail_score, 1),
        "shared_slots": shared_slot_labels,
        "shared_days": shared_days,
        "caregiver_days": sorted(caregiver_avail.keys()),
        "client_days": sorted(client_avail.keys()),
        "caregiver_slot_count": len(caregiver_slots),
        "client_slot_count": len(client_slots),
        "shared_slot_count": len(shared_slots),
    }
    total += avail_score

    # ── 3. Location / ZIP match (10 pts) ────────────────────────────────────
    # Uses real haversine distance between ZIP code centroids (stdlib-only,
    # no network calls).  Falls back to the old prefix-match heuristic when
    # a ZIP is not found in the bundled dataset (invalid / non-US ZIP).
    from .zip_distance import zip_distance_miles, location_score_from_distance

    caregiver_zip = (caregiver.base_zip_code or "").strip()
    client_zip = (client.base_zip_code or "").strip()
    same_zip = bool(caregiver_zip and client_zip and caregiver_zip.split("-")[0] == client_zip.split("-")[0])

    distance_miles = None
    loc_score = 0.0

    if caregiver_zip and client_zip:
        distance_miles = zip_distance_miles(caregiver_zip, client_zip)
        if distance_miles is not None:
            # Real distance available — use tiered scoring
            loc_score = location_score_from_distance(distance_miles)
        else:
            # ZIP not in dataset — graceful fallback to old prefix heuristic
            if same_zip:
                loc_score = 10.0
            elif caregiver_zip[:3] == client_zip[:3]:
                loc_score = 5.0

    details["location"] = {
        "score": round(loc_score, 1),
        "caregiver_zip": caregiver_zip,
        "client_zip": client_zip,
        "same_zip": same_zip,
        "distance_miles": distance_miles,
    }
    total += loc_score

    # ── 4. Transportation compatibility (5 pts) ──────────────────────────────
    caregiver_transport = set(caregiver.transportation or [])
    transport_score = 5.0 if ("licensed_driver" in caregiver_transport or
                               "vehicle_access" in caregiver_transport) else 0.0
    details["transportation"] = {
        "score": round(transport_score, 1),
        "caregiver_transport": sorted(caregiver_transport),
    }
    total += transport_score

    # ── 5. Language match (5 pts) ────────────────────────────────────────────
    caregiver_langs = set(caregiver.languages_spoken or [])
    client_langs = set(client.languages_preferred or [])
    lang_overlap = caregiver_langs & client_langs
    lang_score = 5.0 if lang_overlap else 0.0
    details["language"] = {
        "score": round(lang_score, 1),
        "shared_languages": sorted(lang_overlap),
    }
    total += lang_score

    final_score = round(min(total, 100.0), 1)

    # ── Build human-readable reasoning ───────────────────────────────────────
    reasoning_parts = []
    if tag_overlap:
        reasoning_parts.append(
            f"overlapping skills/needs: {', '.join(sorted(tag_overlap))}"
        )
    if selected_tags:
        reasoning_parts.append(
            f"selected tags: {', '.join(selected_tags)}"
        )
    if shared_days:
        reasoning_parts.append(
            f"availability overlap on: {', '.join(sorted(shared_days))}"
        )
    if same_zip:
        reasoning_parts.append("same ZIP code")
    elif distance_miles is not None and loc_score > 0:
        reasoning_parts.append(f"approximately {distance_miles} miles away")
    elif loc_score > 0:
        reasoning_parts.append("nearby ZIP code area")
    if lang_overlap:
        reasoning_parts.append(
            f"shared languages: {', '.join(sorted(lang_overlap))}"
        )
    if transport_score > 0:
        reasoning_parts.append("caregiver has transportation")

    if reasoning_parts:
        ai_reasoning = (
            "This caregiver may be a strong match because they have "
            + ", ".join(reasoning_parts) + "."
        )
    else:
        ai_reasoning = (
            "Compatibility was not determined based on available profile data. "
            "Further review is recommended."
        )

    return {
        "score": final_score,
        "details": details,
        "ai_reasoning": ai_reasoning,
    }


# ==============================================
# ChatGPT AI-Enhanced Scoring
# ==============================================

def _build_chatgpt_prompt(caregiver, client):
    """
    Build a structured prompt payload for ChatGPT match scoring.

    Privacy note: only anonymized profile attributes (skills, availability,
    languages, ZIP, care needs) are sent — no names, emails, or IDs.

    Returns:
        tuple of (caregiver_data, client_data, distance_miles)
        where distance_miles is a float (computed haversine distance) or None.
    """
    from .zip_distance import zip_distance_miles as _zdm

    caregiver_zip = (caregiver.base_zip_code or "").strip()
    client_zip = (client.base_zip_code or "").strip()

    # Compute real distance so ChatGPT gets a factual number, not a guess
    distance_miles = _zdm(caregiver_zip, client_zip) if (caregiver_zip and client_zip) else None

    caregiver_data = {
        "experience_with": caregiver.experience_with or [],
        "languages_spoken": caregiver.languages_spoken or [],
        "availability": caregiver.availability or {},
        "transportation": caregiver.transportation or [],
        "zip_code": caregiver_zip,
        "hours_looking_for": getattr(caregiver, "hours_looking_for", ""),
        "desired_hours_per_week": getattr(caregiver, "desired_hours_per_week", None),
        "pathogen_protocols": caregiver.pathogen_protocols or [],
        "bio_excerpt": (caregiver.bio or "")[:300],
    }
    client_data = {
        "care_needs": client.care_needs or [],
        "languages_preferred": client.languages_preferred or [],
        "availability": client.availability or {},
        "zip_code": client_zip,
        "desired_hours_per_week": getattr(client, "hours_per_week", None),
        "pathogen_protocol_preferences": client.pathogen_protocol_preferences or [],
        "additional_care_needs": (client.additional_care_needs or "")[:300],
    }
    return caregiver_data, client_data, distance_miles


def _call_chatgpt_match_score(caregiver, client):
    """
    Call the OpenAI Chat Completions API to evaluate a caregiver–client pair.

    Returns a dict with keys:
        score       (float 0–100)
        reasoning   (str)
        strengths   (list of str)
        concerns    (list of str)
        source      "chatgpt"

    Returns None if the API is disabled, key is missing, or the call fails.
    The caller should fall back to local scoring when None is returned.
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    model = getattr(settings, "OPENAI_MATCH_MODEL", "gpt-4o-mini")
    timeout = getattr(settings, "OPENAI_MATCH_TIMEOUT", 15)
    enabled = getattr(settings, "OPENAI_MATCH_ENABLED", True)

    if not enabled or not api_key:
        return None

    caregiver_data, client_data, distance_miles = _build_chatgpt_prompt(caregiver, client)

    # Format distance context so the model gets a hard fact, not a ZIP-inference guess
    if distance_miles is not None:
        distance_context = f"Computed geographic distance: {distance_miles} miles apart."
    else:
        distance_context = "Geographic distance: unknown (ZIP code not in dataset)."

    system_prompt = (
        "You are an expert caregiver-client matching specialist for a home care registry. "
        "Evaluate the compatibility between a caregiver and a client based on their anonymized "
        "profile attributes and return ONLY a valid JSON object. "
        "Do NOT include markdown formatting or code blocks in your response. "
        "The JSON must have exactly these keys:\n"
        "  score     — integer 0-100 representing overall compatibility\n"
        "  reasoning — a single paragraph (2-4 sentences) explaining the match quality\n"
        "  strengths — a JSON array of up to 4 short strings describing match strengths\n"
        "  concerns  — a JSON array of up to 3 short strings describing potential gaps or concerns\n"
        "Be concise and specific. Focus on care needs alignment, availability, language, and location. "
        "Use the provided computed distance rather than guessing proximity from ZIP codes."
    )

    user_message = (
        f"Caregiver profile:\n{json.dumps(caregiver_data, indent=2)}\n\n"
        f"Client profile:\n{json.dumps(client_data, indent=2)}\n\n"
        f"{distance_context}\n\n"
        "Rate the compatibility and return a JSON object as described."
    )

    if not _OPENAI_AVAILABLE or OpenAI is None:
        logger.warning("openai package not installed — ChatGPT matching disabled.")
        return None

    try:
        client_api = OpenAI(api_key=api_key, timeout=timeout)
        response = client_api.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code blocks if the model still wraps the response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)

        score = max(0.0, min(100.0, float(data.get("score", 50))))
        reasoning = str(data.get("reasoning", "")).strip()
        strengths = [str(s) for s in data.get("strengths", [])]
        concerns = [str(c) for c in data.get("concerns", [])]

        return {
            "score": round(score, 1),
            "reasoning": reasoning,
            "strengths": strengths,
            "concerns": concerns,
            "source": "chatgpt",
        }

    except Exception as exc:
        logger.warning(
            "ChatGPT match scoring failed (%s: %s) — falling back to local scoring.",
            type(exc).__name__,
            exc,
        )
        return None


def compute_ai_enhanced_match_score(caregiver, client, selected_tag_ids=None):
    """
    Compute an AI-enhanced compatibility score between a caregiver and client.

    Strategy:
      1. Always run the local heuristic scorer first (fast, no API cost).
      2. Attempt a ChatGPT-enhanced evaluation on top.
      3. If ChatGPT succeeds, replace the score and reasoning with the AI result
         while preserving the local heuristic breakdown for transparency.
      4. If ChatGPT is unavailable or fails, return the local result unchanged.

    Args:
        caregiver: CaregiverProfile instance
        client: ClientProfile instance
        selected_tag_ids: optional list of Tag PKs explicitly selected

    Returns:
        dict with keys:
            score         (float 0–100)
            details       (dict with per-factor local breakdown + optional chatgpt key)
            ai_reasoning  (str — ChatGPT reasoning or local reasoning)
    """
    # 1. Local baseline score
    local_result = compute_match_score(caregiver, client, selected_tag_ids=selected_tag_ids)

    # 2. ChatGPT enhancement
    chatgpt_result = _call_chatgpt_match_score(caregiver, client)

    if chatgpt_result:
        # Merge: keep local details for transparency, add chatgpt key
        enhanced_details = dict(local_result["details"])
        enhanced_details["chatgpt"] = {
            "score": chatgpt_result["score"],
            "strengths": chatgpt_result["strengths"],
            "concerns": chatgpt_result["concerns"],
        }

        # Build enhanced reasoning combining ChatGPT narrative with local facts
        reasoning_parts = []
        if chatgpt_result["reasoning"]:
            reasoning_parts.append(chatgpt_result["reasoning"])
        if chatgpt_result["strengths"]:
            reasoning_parts.append(
                "Key strengths: " + "; ".join(chatgpt_result["strengths"]) + "."
            )
        if chatgpt_result["concerns"]:
            reasoning_parts.append(
                "Points to review: " + "; ".join(chatgpt_result["concerns"]) + "."
            )

        return {
            "score": chatgpt_result["score"],
            "details": enhanced_details,
            "ai_reasoning": " ".join(reasoning_parts),
            "ai_source": "chatgpt",
        }

    # 3. Fallback to local result
    local_result["ai_source"] = "local_scoring_model"
    return local_result


def _selected_tag_keys(tag_ids):
    """
    Given a list of Tag PKs, return a set of normalized profile keys.

    Tag slugs use hyphens (e.g. 'assistive-technology') but profile JSON
    fields (experience_with / care_needs) use underscores
    (e.g. 'assistive_technology').  This helper resolves the slugs and
    converts them so we can compare directly against profile data.
    """
    if not tag_ids:
        return set(), []
    from .models import Tag
    tags = Tag.objects.filter(pk__in=tag_ids, is_active=True)
    keys = set()
    labels = []
    for t in tags:
        keys.add(t.name.replace("-", "_"))
        labels.append(t.label)
    return keys, labels


def filter_caregivers_by_tags(client, organization, tag_ids=None, limit=10):
    """Return approved caregivers matching the selected care-need tags.

    This is intentionally a transparent, non-ranked workflow. It is the
    baseline that users can inspect before choosing the AI-assisted ranking
    workflow. The returned shape is deliberately small so the UI cannot imply
    that a compatibility score was calculated.
    """
    from registry.models import OrganizationCaregiver

    selected_keys, _ = _selected_tag_keys(tag_ids)
    caregivers = OrganizationCaregiver.objects.filter(
        organization=organization,
        status="approved",
    ).select_related("caregiver_profile__user_profile")

    results = []
    for relation in caregivers:
        caregiver = relation.caregiver_profile
        skills = set(caregiver.experience_with or [])
        overlaps = sorted(selected_keys & skills) if selected_keys else []
        if selected_keys and not overlaps:
            continue
        results.append({"caregiver": caregiver, "criteria_matches": overlaps})

    results.sort(key=lambda item: item["caregiver"].user_profile.display_name.lower())
    return results[:limit]


def filter_clients_by_tags(caregiver, organization, tag_ids=None, limit=10):
    """Return approved clients matching selected tags without ranking them."""
    from registry.models import OrganizationClient

    selected_keys, _ = _selected_tag_keys(tag_ids)
    clients = OrganizationClient.objects.filter(
        organization=organization,
        status="approved",
    ).select_related("client_profile__user_profile")

    results = []
    for relation in clients:
        client = relation.client_profile
        needs = set(client.care_needs or [])
        overlaps = sorted(selected_keys & needs) if selected_keys else []
        if selected_keys and not overlaps:
            continue
        results.append({"client": client, "criteria_matches": overlaps})

    results.sort(key=lambda item: item["client"].user_profile.display_name.lower())
    return results[:limit]


def find_best_caregivers_for_client(client, organization, limit=5, tag_ids=None):
    """
    Score all approved caregivers in the organization against a client
    and return only those whose experience_with contains at least one of
    the selected tag keys, sorted by score descending.

    Two-phase strategy (mirrors find_best_pair_for_staff):
      Phase 1 — fast local scoring over all tag-filtered candidates (no API).
      Phase 2 — ChatGPT-enhance only the top `limit` results to control cost
                 and avoid unbounded sequential OpenAI calls.

    Returns list of dicts: [{caregiver, score, details, ai_reasoning,
                              criteria_matches}, ...]
    """
    from registry.models import OrganizationCaregiver
    org_caregivers = OrganizationCaregiver.objects.filter(
        organization=organization,
        status="approved",
    ).select_related("caregiver_profile__user_profile")

    selected_keys, selected_labels = _selected_tag_keys(tag_ids)

    # Phase 1: local scoring over all tag-filtered candidates (fast, no API cost)
    local_results = []
    for rel in org_caregivers:
        caregiver = rel.caregiver_profile
        cg_skills = set(caregiver.experience_with or [])
        # Strict filter: only include caregivers who have at least one
        # of the selected criteria in their experience_with list.
        if selected_keys:
            criteria_matches = sorted(selected_keys & cg_skills)
            if not criteria_matches:
                continue
        else:
            criteria_matches = []

        result = compute_match_score(caregiver, client, selected_tag_ids=tag_ids)
        local_results.append({
            "caregiver": caregiver,
            "score": result["score"],
            "details": result["details"],
            "ai_reasoning": result["ai_reasoning"],
            "ai_source": "local_scoring_model",
            "criteria_matches": criteria_matches,
        })

    local_results.sort(key=lambda x: x["score"], reverse=True)
    top_local = local_results[:limit]

    # Phase 2: ChatGPT-enhance only the top candidates
    enhanced_results = []
    for entry in top_local:
        ai_result = compute_ai_enhanced_match_score(
            entry["caregiver"], client, selected_tag_ids=tag_ids
        )
        enhanced_results.append({
            "caregiver": entry["caregiver"],
            "score": ai_result["score"],
            "details": ai_result["details"],
            "ai_reasoning": ai_result["ai_reasoning"],
            "ai_source": ai_result.get("ai_source", "local_scoring_model"),
            "criteria_matches": entry["criteria_matches"],
        })

    enhanced_results.sort(key=lambda x: x["score"], reverse=True)
    return enhanced_results


def find_best_clients_for_caregiver(caregiver, organization, limit=5, tag_ids=None):
    """
    Score all approved clients in the organization against a caregiver
    and return only those whose care_needs contains at least one of the
    selected tag keys, sorted by score descending.

    Two-phase strategy (mirrors find_best_pair_for_staff):
      Phase 1 — fast local scoring over all tag-filtered candidates (no API).
      Phase 2 — ChatGPT-enhance only the top `limit` results to control cost
                 and avoid unbounded sequential OpenAI calls.

    Returns list of dicts: [{client, score, details, ai_reasoning,
                              criteria_matches}, ...]
    """
    from registry.models import OrganizationClient
    org_clients = OrganizationClient.objects.filter(
        organization=organization,
        status="approved",
    ).select_related("client_profile__user_profile")

    selected_keys, selected_labels = _selected_tag_keys(tag_ids)

    # Phase 1: local scoring over all tag-filtered candidates (fast, no API cost)
    local_results = []
    for rel in org_clients:
        client = rel.client_profile
        client_needs = set(client.care_needs or [])
        # Strict filter: only include clients who need at least one of
        # the selected criteria.
        if selected_keys:
            criteria_matches = sorted(selected_keys & client_needs)
            if not criteria_matches:
                continue
        else:
            criteria_matches = []

        result = compute_match_score(caregiver, client, selected_tag_ids=tag_ids)
        local_results.append({
            "client": client,
            "score": result["score"],
            "details": result["details"],
            "ai_reasoning": result["ai_reasoning"],
            "ai_source": "local_scoring_model",
            "criteria_matches": criteria_matches,
        })

    local_results.sort(key=lambda x: x["score"], reverse=True)
    top_local = local_results[:limit]

    # Phase 2: ChatGPT-enhance only the top candidates
    enhanced_results = []
    for entry in top_local:
        ai_result = compute_ai_enhanced_match_score(
            caregiver, entry["client"], selected_tag_ids=tag_ids
        )
        enhanced_results.append({
            "client": entry["client"],
            "score": ai_result["score"],
            "details": ai_result["details"],
            "ai_reasoning": ai_result["ai_reasoning"],
            "ai_source": ai_result.get("ai_source", "local_scoring_model"),
            "criteria_matches": entry["criteria_matches"],
        })

    enhanced_results.sort(key=lambda x: x["score"], reverse=True)
    return enhanced_results


def find_best_pair_for_staff(organization, limit=5, tag_ids=None, caregiver=None, client=None):
    """
    For staff AI-assisted matching:
    - If both caregiver and client given, return one scored result.
    - If only caregiver given, score against all clients.
    - If only client given, score against all caregivers.
    - If neither given, score all approved caregivers × clients and return top N.

    For the full cross-scoring path, local scoring is used first to rank all pairs,
    then the top results are ChatGPT-enhanced to control API costs.

    Returns list of dicts: [{caregiver, client, score, details, ai_reasoning}, ...]
    """
    from registry.models import OrganizationCaregiver, OrganizationClient

    if caregiver and client:
        result = compute_ai_enhanced_match_score(caregiver, client, selected_tag_ids=tag_ids)
        return [{
            "caregiver": caregiver,
            "client": client,
            "score": result["score"],
            "details": result["details"],
            "ai_reasoning": result["ai_reasoning"],
        }]

    if caregiver:
        clients = find_best_clients_for_caregiver(caregiver, organization, limit=limit, tag_ids=tag_ids)
        return [{"caregiver": caregiver, **c} for c in clients]

    if client:
        caregivers = find_best_caregivers_for_client(client, organization, limit=limit, tag_ids=tag_ids)
        return [{"client": client, **c} for c in caregivers]

    # Full cross-scoring:
    # Phase 1 — local scoring to rank all pairs cheaply.
    # Phase 2 — ChatGPT-enhance only the top `limit` pairs.
    org_caregivers = list(
        OrganizationCaregiver.objects.filter(
            organization=organization, status="approved"
        ).select_related("caregiver_profile__user_profile")
    )
    org_clients = list(
        OrganizationClient.objects.filter(
            organization=organization, status="approved"
        ).select_related("client_profile__user_profile")
    )

    # Phase 1: fast local scoring over all pairs
    local_results = []
    for cg_rel in org_caregivers:
        for cl_rel in org_clients:
            result = compute_match_score(
                cg_rel.caregiver_profile,
                cl_rel.client_profile,
                selected_tag_ids=tag_ids,
            )
            local_results.append({
                "caregiver": cg_rel.caregiver_profile,
                "client": cl_rel.client_profile,
                "score": result["score"],
                "details": result["details"],
                "ai_reasoning": result["ai_reasoning"],
            })

    local_results.sort(key=lambda x: x["score"], reverse=True)
    top_local = local_results[:limit]

    # Phase 2: ChatGPT-enhance only the top candidates
    enhanced_results = []
    for entry in top_local:
        ai_result = compute_ai_enhanced_match_score(
            entry["caregiver"], entry["client"], selected_tag_ids=tag_ids
        )
        enhanced_results.append({
            "caregiver": entry["caregiver"],
            "client": entry["client"],
            "score": ai_result["score"],
            "details": ai_result["details"],
            "ai_reasoning": ai_result["ai_reasoning"],
        })

    enhanced_results.sort(key=lambda x: x["score"], reverse=True)
    return enhanced_results


# ==============================================
# Notification Helpers (Stage 9)
# ==============================================

def _notify_on_match_created(match):
    """
    Send notifications when a match is first created.

    When caregiver initiates → notify client + staff.
    When client initiates → notify caregiver + staff.
    When staff/ai initiates → notify caregiver + client.
    """
    caregiver_profile = match.caregiver
    client_profile = match.client
    org = match.organization

    caregiver_user = caregiver_profile.user_profile
    client_user = client_profile.user_profile

    if match.initiated_by == "caregiver":
        _send_notification(
            recipient=client_user,
            notification_type="match_request",
            subject=f"New match request from {caregiver_user.display_name}",
            message=(
                f"{caregiver_user.display_name} has requested to be matched with you "
                f"through {org.name}. Please review this request in your dashboard."
            ),
            match=match,
        )
        _notify_staff(
            organization=org,
            notification_type="match_request",
            subject=f"New match inquiry: {caregiver_user.display_name} ↔ {client_user.display_name}",
            message=(
                f"{caregiver_user.display_name} (caregiver) has requested a match with "
                f"{client_user.display_name} (client)."
            ),
            match=match,
        )

    elif match.initiated_by == "client":
        _send_notification(
            recipient=caregiver_user,
            notification_type="match_request",
            subject=f"New match request from {client_user.display_name}",
            message=(
                f"{client_user.display_name} has requested to be matched with you "
                f"through {org.name}. Please review this request in your dashboard."
            ),
            match=match,
        )
        _notify_staff(
            organization=org,
            notification_type="match_request",
            subject=f"New match inquiry: {caregiver_user.display_name} ↔ {client_user.display_name}",
            message=(
                f"{client_user.display_name} (client) has requested a match with "
                f"{caregiver_user.display_name} (caregiver)."
            ),
            match=match,
        )

    elif match.initiated_by in ("staff", "ai"):
        _send_notification(
            recipient=caregiver_user,
            notification_type="match_request",
            subject=f"New proposed match from {org.name}",
            message=(
                f"{org.name} has proposed a match between you and "
                f"{client_user.display_name}. Please review and respond in your dashboard."
            ),
            match=match,
        )
        _send_notification(
            recipient=client_user,
            notification_type="match_request",
            subject=f"New proposed match from {org.name}",
            message=(
                f"{org.name} has proposed a match between you and "
                f"{caregiver_user.display_name}. Please review and respond in your dashboard."
            ),
            match=match,
        )


def _notify_on_party_response(match, party, response):
    """Send notifications when a party responds to a match."""
    caregiver_user = match.caregiver.user_profile
    client_user = match.client.user_profile
    org = match.organization

    if match.status == "active":
        # Notify both parties the match is now active
        for recipient in [caregiver_user, client_user]:
            _send_notification(
                recipient=recipient,
                notification_type="match_active",
                subject="Your match is now active!",
                message=(
                    f"All parties have approved the match between "
                    f"{caregiver_user.display_name} and {client_user.display_name} "
                    f"through {org.name}."
                ),
                match=match,
            )
        return

    if match.status == "declined":
        for recipient in [caregiver_user, client_user]:
            _send_notification(
                recipient=recipient,
                notification_type="match_declined",
                subject="A match has been declined",
                message=(
                    f"The match between {caregiver_user.display_name} and "
                    f"{client_user.display_name} was declined by {party}."
                ),
                match=match,
            )
        return

    # Still pending — notify the remaining parties
    party_labels = {"caregiver": caregiver_user.display_name, "client": client_user.display_name}
    if party == "caregiver" and response == "approved":
        _send_notification(
            recipient=client_user,
            notification_type="match_approved",
            subject=f"{caregiver_user.display_name} approved the match",
            message=(
                f"{caregiver_user.display_name} approved the match. "
                f"Awaiting your response."
            ),
            match=match,
        )
    elif party == "client" and response == "approved":
        _send_notification(
            recipient=caregiver_user,
            notification_type="match_approved",
            subject=f"{client_user.display_name} approved the match",
            message=(
                f"{client_user.display_name} approved the match. "
                f"Awaiting your response."
            ),
            match=match,
        )


def _notify_staff(*, organization, notification_type, subject, message, match):
    """Notify all active staff/admin in an organization."""
    from organizations.models import OrganizationStaff
    staff_rels = OrganizationStaff.objects.filter(
        organization=organization,
        status="active",
    ).select_related("staff_profile__user_profile")
    for rel in staff_rels:
        _send_notification(
            recipient=rel.staff_profile.user_profile,
            notification_type=notification_type,
            subject=subject,
            message=message,
            match=match,
        )


def _send_notification(*, recipient, notification_type, subject, message, match=None):
    """
    Create an in-app notification and attempt to send an email.
    If email fails, silently falls back to the DB notification only.
    """
    from .models import Notification
    from django.core.mail import send_mail
    from django.conf import settings

    # Always create in-app notification
    notif = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        subject=subject,
        message=message,
        match=match,
    )

    # Attempt email delivery — fail gracefully
    try:
        if recipient.auth_email:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.auth_email],
                fail_silently=True,
            )
    except Exception:
        logger.warning(
            "Email notification failed for %s — in-app notification was saved.",
            recipient.auth_email,
        )

    return notif

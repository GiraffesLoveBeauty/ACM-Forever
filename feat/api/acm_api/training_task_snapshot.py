"""Luogu observation evidence. Observation timestamps are never submission times."""


def observe(previous, *, accepted, requested_at, observed_at, known_ac=False):
    """Only a validated complete page may supply negative evidence.

    Keep the negative preceding the FIRST positive. Later absences cannot move
    an old positive across a task boundary. Request order fences stale workers.
    """
    result = dict(previous or {})
    if requested_at < result.get("last_request_at", 0):
        return result
    if not result:
        result.update(baseline_at=observed_at, baseline_state="accepted" if accepted or known_ac else "not_accepted")
    result.update(last_request_at=requested_at, last_checked_at=observed_at)
    if accepted or known_ac:
        if not result.get("first_seen_at"):
            result.update(first_seen_at=observed_at,
                          source="luogu_public_practice" if accepted else "local_luogu_ac_set")
        result["conflict"] = not accepted
    elif result.get("first_seen_at"):
        result["conflict"] = True
    else:
        result["last_absent_at"] = int(requested_at)
        result["conflict"] = False
    return result


def local_positive(now):
    # Reading an existing AC is positive evidence as of NOW, never evidence that
    # it was already accepted at an earlier task start or deadline.
    return {"baseline_at": now, "baseline_state": "accepted", "first_seen_at": now,
            "source": "local_luogu_ac_set", "last_checked_at": 0, "last_request_at": 0}


def classify(snapshot, *, starts_at, due_at, rule, problem_id, review=None):
    """Return (historical, on_time, late, timing_unknown) using the stored policy."""
    if not snapshot or not snapshot.get("first_seen_at"):
        return None, None, None, None
    seen, absent = snapshot["first_seen_at"], snapshot.get("last_absent_at")
    public_positive = snapshot.get("source") == "luogu_public_practice"
    proof = {"platform": "luogu", "problem_id": problem_id, "accepted_at": None,
             "observed_at": seen, "last_not_accepted_at": absent,
             "source": snapshot.get("source", "luogu_public_practice"), "evidence_type": "snapshot"}
    if review:
        manual = {**proof, "source": "admin_review", "evidence_type": "manual",
                  "reviewed_at": review["reviewed_at"], "reason": review["reason"]}
        if review["decision"] == "on_time":
            return None, manual, None, None
        if due_at == review.get("due_at", due_at):
            return None, None, manual, None
        # A late decision used an older deadline. Existence by the review time
        # proves completion before an extended deadline; otherwise re-use the
        # original observations instead of asserting it is still late.
        if review["reviewed_at"] <= due_at:
            return None, manual, None, None
    if seen < starts_at:
        return proof, None, None, None
    if seen <= due_at and (rule == "historical_ac" or public_positive and absent is not None and starts_at <= absent <= seen):
        return None, proof, None, None
    if public_positive and seen > due_at and absent is not None and due_at <= absent <= seen:
        return None, None, proof, None
    return None, None, None, proof

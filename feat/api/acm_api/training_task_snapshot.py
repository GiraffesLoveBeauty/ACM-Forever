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


def classify(snapshot, *, starts_at=None, due_at=None, rule=None, problem_id, review=None):
    """Luogu completion depends only on historical AC, never on task dates.

    Legacy policy/review arguments remain accepted while stored evidence is
    reclassified. An observation time is never exposed as a submission time.
    """
    if not snapshot or not snapshot.get("first_seen_at"):
        return None, None, None, None
    proof = {"platform": "luogu", "problem_id": problem_id, "accepted_at": None,
             "observed_at": snapshot["first_seen_at"],
             "source": snapshot.get("source", "luogu_public_practice"),
             "evidence_type": "historical_ac"}
    return proof, None, None, None

"""Evaluate immutable rule+model predictions against literal human reviewed=true."""
from label_pipeline import evaluate, TAXONOMY, MAPPING, validate_id_list, unique
from .adapter import canonical_identity, human_confirmed


def indexed(rows, name):
    result = {}
    for row in rows:
        key = canonical_identity(row)[3]
        if key in result:
            raise ValueError(f"Duplicate {name} identity")
        result[key] = row
    return result


def original_labels(pred):
    if human_confirmed(pred) or pred.get("prediction_origin") not in {"ai", "rule_only"}:
        raise ValueError("Evaluate predictions.jsonl, not manually corrected/merged labels")
    if pred.get("taxonomy_version") != TAXONOMY["version"]:
        raise ValueError("Prediction taxonomy mismatch")
    if pred["prediction_origin"] == "rule_only":
        return {"problem_key": pred["problem_key"],
                "specific_tag_ids": validate_id_list(pred["specific_tag_ids"], "specific", "rule labels"),
                "provisional_tag_ids": validate_id_list(pred["provisional_tag_ids"], "provisional", "rule labels")}
    specific = validate_id_list(pred["specific_tag_ids"], "specific", "model labels")
    provisional = validate_id_list(pred["provisional_tag_ids"], "provisional", "model labels")
    exact = validate_id_list(pred["cf_exact_tag_ids"], "specific", "CF exact")
    rule_provisional = validate_id_list(pred["rule_provisional_tag_ids"], "provisional", "CF provisional")
    resolved = pred["resolved_cf_hints"]
    if not isinstance(resolved, dict):
        raise ValueError("Expected normalized CF resolution object")
    if pred["platform"] == "atcoder" and (resolved or exact or rule_provisional):
        raise ValueError("AtCoder prediction cannot contain CF rule labels")
    removed = set()
    resolved_labels = []
    for hint, ids in resolved.items():
        if hint not in pred["cf_unresolved_hints"] or hint not in MAPPING["clue"]:
            raise ValueError("Invalid CF resolution")
        values = validate_id_list(ids, "specific", "resolved labels")
        if not values:
            raise ValueError("Empty CF resolution")
        resolved_labels.extend(values)
        removed.add(MAPPING["clue"][hint]["provisional_tag_id"])
    combined = unique(exact + specific + resolved_labels)
    combined_provisional = unique([x for x in rule_provisional if x not in removed] + provisional)
    if pred.get("evaluation_specific_tag_ids") != combined or pred.get("evaluation_provisional_tag_ids") != combined_provisional:
        raise ValueError("Stored evaluation labels differ from immutable rule/model prediction")
    return {"problem_key": pred["problem_key"], "specific_tag_ids": combined,
            "provisional_tag_ids": combined_provisional}


def report(predictions, golds, *, manifest=None, errors=None):
    by_key = indexed(predictions, "prediction")
    gold_by_key = indexed(golds, "gold")
    profile_ids = {x.get("profile_id") for x in predictions}
    if len(profile_ids) > 1:
        raise ValueError("Mixed prediction profiles")
    selected = indexed(manifest["selected"], "manifest") if manifest else {}
    labels = {}
    for key, pred in by_key.items():
        if not isinstance(pred.get("content_hash"), str) or not pred["content_hash"]:
            raise ValueError("Prediction content hash missing")
        labels[key] = original_labels(pred)
        if manifest:
            if key not in selected or selected[key]["content_hash"] != pred["content_hash"]:
                raise ValueError("Prediction not in the same frozen dataset version")
            if selected[key].get("annotation_input_hash") != pred.get("annotation_input_hash"):
                raise ValueError("Prediction evidence hash differs from manifest")
            if pred.get("profile_id") != manifest["profile_id"]:
                raise ValueError("Prediction profile differs from manifest")
    reviewed = []
    legacy_count = 0
    for key, gold in gold_by_key.items():
        flag = gold.get("reviewed", False)
        if not isinstance(flag, bool):
            raise ValueError("reviewed must be a JSON boolean")
        if flag is not True:
            continue
        if gold.get("taxonomy_version") != TAXONOMY["version"]:
            raise ValueError("Gold taxonomy mismatch")
        validate_id_list(gold["accepted_specific_tag_ids"], "specific", "gold labels")
        validate_id_list(gold.get("accepted_provisional_tag_ids", []), "provisional", "gold provisional")
        reference = selected.get(key) if manifest else by_key.get(key)
        if not reference:
            raise ValueError("Reviewed gold outside prediction dataset")
        if gold.get("content_hash"):
            if gold["content_hash"] != reference["content_hash"]:
                raise ValueError("Gold content hash mismatch")
        elif manifest:
            legacy_count += 1
        else:
            raise ValueError("Reviewed gold without hash requires a frozen manifest")
        reviewed.append(gold)
    failure_keys = {x.get("problem_key") for x in (errors or []) if x.get("problem_key")} - set(by_key)
    scope = set(selected) if manifest else set(by_key) | failure_keys
    missing_reviewed = [g["problem_key"] for g in reviewed if g["problem_key"] not in labels]
    # Missing predictions remain in the denominator and contribute false negatives.
    scoring = list(labels.values()) + [{"problem_key": k, "specific_tag_ids": [], "provisional_tag_ids": []} for k in missing_reviewed]
    quality = evaluate(scoring, reviewed)
    if reviewed:
        quality["exact_match_rate"] = round(sum(
            g["problem_key"] in labels and set(labels[g["problem_key"]]["specific_tag_ids"]) == set(g["accepted_specific_tag_ids"])
            for g in reviewed) / len(reviewed), 4)
    else:
        quality.update(micro_precision=None, micro_recall=None, micro_f1=None, exact_match_rate=None)
    total = len(scope)
    successful = len(by_key)
    stats = {"selected_count": total, "prediction_count": successful,
             "prediction_coverage": successful / total if total else None,
             "specific_coverage_all_selected": sum(bool(p["specific_tag_ids"]) for p in labels.values()) / total if total else None,
             "provisional_rate_all_selected": sum(bool(p["provisional_tag_ids"]) for p in labels.values()) / total if total else None,
             "pending_review_rate_all_selected": sum(p.get("human_review_status") == "pending_review" for p in predictions) / total if total else None,
             "failure_count": len(failure_keys & scope), "failure_rate": len(failure_keys & scope) / total if total else None,
             "missing_prediction_count": len(scope - set(by_key)), "missing_reviewed_prediction_count": len(missing_reviewed)}
    platform_counts = {platform: sum(key.startswith(platform + ":") for key in scope) for platform in ("codeforces", "atcoder")}
    return {"taxonomy_version": TAXONOMY["version"],
            "dataset_sha256": manifest["profile"].get("dataset_sha256") if manifest else None,
            "profile_id": manifest["profile_id"] if manifest else next(iter(profile_ids), None),
            "quality_on_reviewed": quality,
            "descriptive_all_selected": stats, "platform_counts": platform_counts,
            "legacy_gold_associated_via_manifest": legacy_count,
            "note": "仅人工 reviewed=true 为答案；质量指标评估不可变规则+模型预测。失败题保留在分母中；缺少预测不视为完全匹配。"}

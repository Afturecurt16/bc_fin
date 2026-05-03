from __future__ import annotations


def tokenize_csv(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set()
    return {
        chunk.strip().lower()
        for chunk in raw_value.replace(";", ",").split(",")
        if chunk.strip()
    }


def profile_completeness(candidate: dict) -> int:
    fields = [
        candidate.get("display_name"),
        candidate.get("age"),
        candidate.get("role"),
        candidate.get("bio"),
        candidate.get("company"),
        candidate.get("avatar_file_id"),
    ]
    return sum(1 for value in fields if value)


def calculate_score(viewer: dict, viewer_pref: dict, candidate: dict, candidate_pref: dict, candidate_linkedin_verified: bool) -> int:
    score = 0

    viewer_industries = tokenize_csv(viewer_pref.get("industries"))
    candidate_industry = tokenize_csv(candidate.get("industry"))
    if viewer_industries and viewer_industries & candidate_industry:
        score += 30

    candidate_pref_industries = tokenize_csv(candidate_pref.get("industries"))
    viewer_industry = tokenize_csv(viewer.get("industry"))
    if candidate_pref_industries and candidate_pref_industries & viewer_industry:
        score += 15

    viewer_roles = tokenize_csv(viewer_pref.get("roles"))
    candidate_role = tokenize_csv(candidate.get("role"))
    if viewer_roles and viewer_roles & candidate_role:
        score += 25

    candidate_pref_roles = tokenize_csv(candidate_pref.get("roles"))
    viewer_role = tokenize_csv(viewer.get("role"))
    if candidate_pref_roles and candidate_pref_roles & viewer_role:
        score += 15

    viewer_languages = tokenize_csv(viewer.get("languages"))
    candidate_languages = tokenize_csv(candidate.get("languages"))
    if viewer_languages and candidate_languages and viewer_languages & candidate_languages:
        score += 10

    viewer_location = (viewer.get("location") or "").strip().lower()
    candidate_location = (candidate.get("location") or "").strip().lower()
    geography = (viewer_pref.get("geography") or "").strip().lower()
    if viewer_location and candidate_location and viewer_location == candidate_location:
        score += 10
    elif geography and candidate_location and geography in candidate_location:
        score += 8

    viewer_topics = tokenize_csv(viewer_pref.get("topics"))
    candidate_topics = tokenize_csv(candidate_pref.get("topics"))
    if viewer_topics and candidate_topics and viewer_topics & candidate_topics:
        score += 10

    completeness = profile_completeness(candidate)
    score += min(completeness, 8) * 2

    if candidate_linkedin_verified:
        score += 5

    return score

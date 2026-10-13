"""Mastery calculations compatible with CodeMind's current persistence model."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import exp
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import Problem, ProblemSubmission, StudentLearningProfile, Tag
from ai.tutor import _infer_topics

# Mastery state thresholds
_STRONG_THRESHOLD = 75       # >= 75% acceptance AND >=2 independent solves
_DEVELOPING_THRESHOLD = 40   # >= 40% acceptance, has accepted solves
_NEEDS_PRACTICE = 0          # Has attempted but low acceptance
# Needs Refresh: previously developing/strong but not visited in >21 days (decay <0.5)

# Progression stages ordered
PROGRESSION_STAGES = ["Solved", "Assisted", "Independent", "Transfer", "Mastered"]


def _classify_mastery_status(
    mastery_score: int,
    independent_solves: int,
    accepted_submissions: int,
    needs_refresh: bool,
) -> str:
    """Return one of: Strong | Developing | Needs Practice | Needs Refresh."""
    if needs_refresh:
        return "Needs Refresh"
    if mastery_score >= _STRONG_THRESHOLD and independent_solves >= 2:
        return "Strong"
    if accepted_submissions > 0 and mastery_score >= _DEVELOPING_THRESHOLD:
        return "Developing"
    return "Needs Practice"


def _progression_stage(
    accepted: int,
    independent: int,
    is_verified: bool,
    hints_only: int,
) -> str:
    """Determine highest progression stage reached for this topic."""
    if is_verified:
        return "Mastered"
    if independent >= 1:
        return "Independent"
    if accepted > 0 and hints_only > 0:
        return "Assisted"
    if accepted > 0:
        return "Solved"
    return "Solved"  # fallback; caller only uses this when there are attempts


ERROR_LABELS = {
    "wrong_answer": "Wrong Answer (Logic / Off-by-one)",
    "time_limit": "Time Limit Exceeded (High Complexity)",
    "runtime_error": "Runtime Error (Bounds / Null / Key)",
    "compile_error": "Compilation / Syntax Error",
    "memory_limit": "Memory Limit Exceeded",
}

ERROR_REMEDIATION = {
    "wrong_answer": "Review edge cases and test with boundary inputs. Use the AI Tutor → 'Why Did I Fail?' tab.",
    "time_limit": "Analyse time complexity with AI Tutor → Approach Analyzer. Look for O(n²) loops to optimise.",
    "runtime_error": "Check for index-out-of-bounds, None references, and missing dictionary keys.",
    "compile_error": "Review syntax with the AI Tutor → Code Review & Big-O tab.",
    "memory_limit": "Review data structure choices — avoid storing large intermediate results.",
}


class CurrentMasteryEngine:
    """Evidence summaries built only from real practice submissions."""

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _submissions(student_id: str, db: Session) -> List[ProblemSubmission]:
        return (
            db.query(ProblemSubmission)
            .filter(ProblemSubmission.student_id == student_id)
            .order_by(ProblemSubmission.created_at.desc())
            .all()
        )

    @staticmethod
    def _refresh_topics(submissions: List[ProblemSubmission]) -> set:
        """Return topic names whose accepted submissions are older than 21-day half-life."""
        now = datetime.now(timezone.utc)
        refresh: set = set()
        for item in submissions:
            if item.status != "accepted" or not item.created_at or not item.problem:
                continue
            created = (
                item.created_at.replace(tzinfo=timezone.utc)
                if item.created_at.tzinfo is None
                else item.created_at
            )
            days_ago = max(0, (now - created).total_seconds() / 86400)
            if exp(-days_ago / 21) < 0.5:
                refresh.update(_infer_topics(item.problem))
        return refresh

    # ------------------------------------------------------------------ public API
    def compute_concept_mastery(self, student_id: str, db: Session) -> Dict[str, Any]:
        submissions = self._submissions(student_id, db)
        if not submissions:
            return {
                "status": "insufficient_data",
                "message": "No practice activity recorded yet.",
                "concepts": {},
            }

        refresh_topics = self._refresh_topics(submissions)

        by_topic: Dict[str, List[ProblemSubmission]] = defaultdict(list)
        for submission in submissions:
            if submission.problem:
                for topic in _infer_topics(submission.problem):
                    by_topic[topic].append(submission)

        concepts: Dict[str, Dict[str, Any]] = {}
        for topic, attempts in by_topic.items():
            accepted = [a for a in attempts if a.status == "accepted"]
            independent = [a for a in accepted if not a.hints_used and not a.solution_viewed]
            hints_assisted = [a for a in accepted if a.hints_used and not a.solution_viewed]
            solution_viewed = [a for a in accepted if a.solution_viewed]

            score = round(100 * len(accepted) / len(attempts)) if attempts else 0
            is_verified = len(independent) >= 2 and score >= 70

            needs_refresh = topic in refresh_topics
            status_label = _classify_mastery_status(
                score, len(independent), len(accepted), needs_refresh
            )
            stage = _progression_stage(len(accepted), len(independent), is_verified, len(hints_assisted))

            concepts[topic] = {
                "concept_name": topic,
                "mastery_score": score,
                "mastery_status": status_label,          # Strong | Developing | Needs Practice | Needs Refresh
                "progression_stage": stage,              # Solved | Assisted | Independent | Transfer | Mastered
                "is_verified": is_verified,
                "needs_refresh": needs_refresh,
                "total_problems_practiced": len({a.problem_id for a in attempts}),
                "accepted_submissions": len(accepted),
                "independent_solves": len(independent),
                "hint_assisted_solves": len(hints_assisted),
                "solution_viewed_solves": len(solution_viewed),
                "total_attempts": len(attempts),
            }

        return {"status": "ok", "concepts": concepts}

    def analyze_error_dna(self, student_id: str, db: Session) -> Dict[str, Any]:
        all_subs = self._submissions(student_id, db)
        failed = [s for s in all_subs if s.status != "accepted"]
        counts = Counter(s.status for s in failed)

        total_subs = len(all_subs)
        error_dna = []
        for kind, count in counts.most_common():
            pct = round(count / total_subs * 100, 1) if total_subs else 0
            error_dna.append({
                "type": kind,
                "label": ERROR_LABELS.get(kind, kind.replace("_", " ").title()),
                "count": count,
                "percentage": pct,
                "remediation": ERROR_REMEDIATION.get(kind, "Review this error type with the AI Tutor."),
            })

        # Identify most recurring error per topic
        topic_errors: Dict[str, Counter] = defaultdict(Counter)
        for sub in failed:
            if sub.problem:
                for topic in _infer_topics(sub.problem):
                    topic_errors[topic][sub.status] += 1

        recurring_by_topic = []
        for topic, counter in sorted(topic_errors.items(), key=lambda x: -sum(x[1].values())):
            most_common_type, most_common_count = counter.most_common(1)[0]
            recurring_by_topic.append({
                "topic": topic,
                "error_type": most_common_type,
                "error_label": ERROR_LABELS.get(most_common_type, most_common_type),
                "count": most_common_count,
            })

        return {
            "status": "ok" if failed else "insufficient_data",
            "total_failed_submissions": len(failed),
            "error_dna": error_dna,
            "recurring_by_topic": recurring_by_topic[:5],  # top 5 problem areas
        }

    def track_approach_fingerprint(self, student_id: str, db: Session) -> Dict[str, Any]:
        submissions = self._submissions(student_id, db)
        if not submissions:
            return {
                "status": "insufficient_data",
                "accepted_submissions": 0,
                "hint_dependency_ratio": 0.0,
                "stage": "Developing",
                "progression": {
                    "Solved": 0,
                    "Assisted": 0,
                    "Independent": 0,
                    "Transfer": 0,
                    "Mastered": 0,
                },
            }

        # Distinct attempted problems
        attempted_prob_ids = {s.problem_id for s in submissions}
        solved_prob_ids = set()
        independent_prob_ids = set()
        assisted_prob_ids = set()

        accepted_submissions_list = []
        for s in submissions:
            if (s.status or "").lower() == "accepted":
                accepted_submissions_list.append(s)

        for p_id in attempted_prob_ids:
            p_subs = [s for s in submissions if s.problem_id == p_id]
            acc_subs = [s for s in p_subs if (s.status or "").lower() == "accepted"]
            if acc_subs:
                solved_prob_ids.add(p_id)
                # Consistent with /api/progress: any independent accepted run makes the problem independent
                has_independent = any(not s.hints_used and not s.solution_viewed for s in acc_subs)
                if has_independent:
                    independent_prob_ids.add(p_id)
                else:
                    assisted_prob_ids.add(p_id)

        # Retrieve concept mastery evaluation and proof of mastery records
        concept_result = self.compute_concept_mastery(student_id, db)
        verified_concepts = set()
        if concept_result.get("status") == "ok":
            for c_name, c_info in concept_result.get("concepts", {}).items():
                if c_info.get("is_verified"):
                    verified_concepts.add(c_name)

        # Check explicit verified proof-of-mastery challenges in learning profile
        prof = db.query(StudentLearningProfile).filter(
            StudentLearningProfile.student_id == student_id
        ).first()
        verified_proof_problems = set()
        if prof and prof.proof_of_mastery:
            for p_info in prof.proof_of_mastery.values():
                if isinstance(p_info, dict) and p_info.get("problem_id"):
                    verified_proof_problems.add(p_info["problem_id"])

        # Determine Mastered and Transfer problems
        # Mastered: problems solved independently within verified concepts OR explicitly verified in proof-of-mastery
        mastered_prob_ids = set(verified_proof_problems & solved_prob_ids)
        transfer_prob_ids = set(mastered_prob_ids)

        for p_id in solved_prob_ids:
            p_subs = [s for s in submissions if s.problem_id == p_id]
            prob_obj = next((s.problem for s in p_subs if s.problem), None)
            if not prob_obj:
                prob_obj = db.query(Problem).filter(Problem.id == p_id).first()
            if prob_obj:
                prob_topics = set(_infer_topics(prob_obj))
                if prob_topics & verified_concepts and p_id in independent_prob_ids:
                    mastered_prob_ids.add(p_id)
                    transfer_prob_ids.add(p_id)
                elif prob_topics & verified_concepts:
                    transfer_prob_ids.add(p_id)

        # Multi-concept transfer evidence
        if len(verified_concepts) > 0 or len(verified_proof_problems) > 0:
            transfer_prob_ids.update(mastered_prob_ids)
        else:
            topics_with_solves = set()
            for p_id in solved_prob_ids:
                p_subs = [s for s in submissions if s.problem_id == p_id]
                prob_obj = next((s.problem for s in p_subs if s.problem), None)
                if not prob_obj:
                    prob_obj = db.query(Problem).filter(Problem.id == p_id).first()
                if prob_obj:
                    for t in _infer_topics(prob_obj):
                        topics_with_solves.add(t)
            if len(topics_with_solves) >= 2 and len(independent_prob_ids) >= 2:
                transfer_prob_ids.update(independent_prob_ids)

        ratio = round(len(assisted_prob_ids) / len(solved_prob_ids), 2) if solved_prob_ids else 0.0

        if mastered_prob_ids:
            stage = "Mastered"
        elif transfer_prob_ids:
            stage = "Transfer"
        elif independent_prob_ids:
            stage = "Independent"
        elif assisted_prob_ids:
            stage = "Assisted"
        elif solved_prob_ids:
            stage = "Solved"
        else:
            stage = "Developing"

        progression = {
            "Solved": len(solved_prob_ids),
            "Assisted": len(assisted_prob_ids),
            "Independent": len(independent_prob_ids),
            "Transfer": len(transfer_prob_ids),
            "Mastered": len(mastered_prob_ids),
        }

        return {
            "status": "ok",
            "accepted_submissions": len(accepted_submissions_list),
            "hint_dependency_ratio": ratio,
            "stage": stage,
            "progression": progression,
        }

    def compute_retention(self, student_id: str, db: Session) -> Dict[str, Any]:
        submissions = self._submissions(student_id, db)
        if not submissions:
            return {"status": "insufficient_data", "concepts_needing_refresh": []}

        refresh_topics = self._refresh_topics(submissions)
        now = datetime.now(timezone.utc)

        # Build decay info per topic
        by_topic: Dict[str, List] = defaultdict(list)
        for sub in submissions:
            if sub.status == "accepted" and sub.created_at and sub.problem:
                created = (
                    sub.created_at.replace(tzinfo=timezone.utc)
                    if sub.created_at.tzinfo is None
                    else sub.created_at
                )
                topics = _infer_topics(sub.problem)
                for t in topics:
                    days_ago = max(0, (now - created).total_seconds() / 86400)
                    by_topic[t].append(days_ago)

        refresh_details = []
        for topic in sorted(refresh_topics):
            if topic in by_topic:
                min_days = min(by_topic[topic])
                retention_pct = round(exp(-min_days / 21) * 100, 1)
                refresh_details.append({
                    "topic": topic,
                    "days_since_last_solve": round(min_days, 1),
                    "retention_score": retention_pct,
                })

        return {
            "status": "ok",
            "concepts_needing_refresh": sorted(refresh_topics),
            "refresh_details": refresh_details,
        }

    def evaluate_proof_of_mastery(self, student_id: str, concept: str, db: Session) -> Dict[str, Any]:
        mastery = self.compute_concept_mastery(student_id, db).get("concepts", {}).get(concept)
        return {"concept": concept, "verified": bool(mastery and mastery["is_verified"]), "evidence": mastery}

    def record_proof_of_mastery_success(self, student_id: str, concept: str, problem_id: str, db: Session) -> bool:
        profile = db.query(StudentLearningProfile).filter(
            StudentLearningProfile.student_id == student_id
        ).first()
        if not profile:
            return False
        proof = dict(profile.proof_of_mastery or {})
        proof[concept] = {"problem_id": problem_id, "verified_at": datetime.now(timezone.utc).isoformat()}
        profile.proof_of_mastery = proof
        db.commit()
        return True

    def get_mastery_recommendations(self, student_id: str, db: Session) -> Dict[str, Any]:
        """Return rich recommendations: one real problem per weak/refresh topic."""
        submissions = self._submissions(student_id, db)
        solved_ids = {s.problem_id for s in submissions if s.status == "accepted"}

        # Get mastery state per topic
        concept_result = self.compute_concept_mastery(student_id, db)
        retention_result = self.compute_retention(student_id, db)

        refresh_topics = set(retention_result.get("concepts_needing_refresh", []))
        concepts = concept_result.get("concepts", {})

        # Rank topics: Needs Refresh > Needs Practice > Developing
        priority_topics: List[Dict] = []
        for topic, info in concepts.items():
            status = info["mastery_status"]
            score = info["mastery_score"]
            if status in ("Needs Refresh", "Needs Practice"):
                priority_topics.append({"topic": topic, "status": status, "score": score})
        priority_topics.sort(key=lambda x: (0 if x["status"] == "Needs Refresh" else 1, x["score"]))

        recommendations: List[Dict[str, Any]] = []
        seen_problem_ids: set = set()

        for entry in priority_topics[:4]:
            topic = entry["topic"]
            status = entry["status"]
            reason_prefix = "🔄 Needs Refresh:" if status == "Needs Refresh" else "📌 Needs Practice:"
            reason = f"{reason_prefix} Strengthen your '{topic}' mastery."

            # Targeted query: match title or tags without full 11,405 table scan
            topic_tag = topic.replace(" ", "-").lower()
            cand = (
                db.query(Problem)
                .filter(
                    Problem.is_active == True,
                    ~Problem.id.in_(solved_ids | seen_problem_ids),
                    Problem.title.ilike(f"%{topic}%"),
                )
                .first()
            )
            if not cand:
                cand = (
                    db.query(Problem)
                    .filter(
                        Problem.is_active == True,
                        ~Problem.id.in_(solved_ids | seen_problem_ids),
                        Problem.tags.any(Tag.name.ilike(f"%{topic_tag}%")),
                    )
                    .first()
                )
            if not cand:
                cand = (
                    db.query(Problem)
                    .filter(
                        Problem.is_active == True,
                        ~Problem.id.in_(solved_ids | seen_problem_ids),
                    )
                    .first()
                )
            if cand:
                seen_problem_ids.add(cand.id)
                recommendations.append({
                    "problem_id": cand.id,
                    "title": cand.title,
                    "difficulty": cand.difficulty,
                    "reason": reason,
                    "target_topic": topic,
                    "mastery_status": status,
                })

        # If nothing from mastery gaps, fill with any unsolved problems
        if not recommendations:
            fallback = (
                db.query(Problem)
                .filter(Problem.is_active == True, ~Problem.id.in_(solved_ids))
                .limit(3)
                .all()
            )
            for p in fallback:
                recommendations.append({
                    "problem_id": p.id,
                    "title": p.title,
                    "difficulty": p.difficulty,
                    "reason": "Foundational interview practice problem.",
                    "target_topic": "General",
                    "mastery_status": "Needs Practice",
                })

        # "What should I do next" summary
        next_action = _derive_next_action(concepts, refresh_topics, recommendations)

        return {
            "status": "ok",
            "recommendations": recommendations,
            "next_action": next_action,
        }

    def get_full_mastery_dashboard(self, student_id: str, db: Session) -> Dict[str, Any]:
        """Single call returning all mastery data needed by the dashboard."""
        concept_result = self.compute_concept_mastery(student_id, db)
        error_dna_result = self.analyze_error_dna(student_id, db)
        approach_result = self.track_approach_fingerprint(student_id, db)
        retention_result = self.compute_retention(student_id, db)
        rec_result = self.get_mastery_recommendations(student_id, db)

        # Build concept list sorted: Needs Refresh first, then Needs Practice, then Developing, then Strong
        status_order = {"Needs Refresh": 0, "Needs Practice": 1, "Developing": 2, "Strong": 3}
        concept_list = sorted(
            concept_result.get("concepts", {}).values(),
            key=lambda c: (status_order.get(c["mastery_status"], 9), -c["mastery_score"]),
        )

        avg_score = (
            round(sum(c["mastery_score"] for c in concept_list) / len(concept_list))
            if concept_list else 0
        )

        return {
            "student_id": student_id,
            "status": "ok" if concept_result["status"] == "ok" else "insufficient_data",
            "overall_mastery_score": avg_score / 100.0,
            "mastery_score": avg_score / 100.0,
            "concepts": concept_list,
            "concept_mastery": {
                "status": concept_result["status"],
                "concepts": concept_list,
            },
            "error_dna": error_dna_result,
            "approach": approach_result,
            "retention": retention_result,
            "recommendations": rec_result,
        }


def _derive_next_action(concepts: dict, refresh_topics: set, recommendations: list) -> Dict[str, Any]:
    """Determine the top 'What should I do next?' action."""
    if not concepts:
        return {
            "type": "start",
            "message": "Start solving your first problem to generate personalized mastery insights!",
            "cta": "Browse Problem Library",
            "cta_action": "showProblemBrowser()",
        }

    # Any refresh needed?
    refreshable = [c for c in concepts.values() if c["mastery_status"] == "Needs Refresh"]
    if refreshable:
        topic = refreshable[0]["concept_name"]
        return {
            "type": "refresh",
            "message": f"Your '{topic}' knowledge is fading (>21 days). Revisit it before you forget!",
            "cta": "Find Refresh Problem",
            "cta_action": "showProblemBrowser()",
            "topic": topic,
        }

    # Needs Practice topics
    gap_topics = [c for c in concepts.values() if c["mastery_status"] == "Needs Practice"]
    if gap_topics:
        topic = gap_topics[0]["concept_name"]
        rec = recommendations[0] if recommendations else None
        return {
            "type": "practice",
            "message": f"Focus on '{topic}' — you need more practice to build real mastery.",
            "cta": "Solve Recommended Problem",
            "cta_action": f"openProblem('{rec['problem_id']}')" if rec else "showProblemBrowser()",
            "topic": topic,
        }

    # All developing — push to independent
    developing = [c for c in concepts.values() if c["mastery_status"] == "Developing"]
    if developing:
        topic = developing[0]["concept_name"]
        return {
            "type": "independence",
            "message": f"You're developing '{topic}'. Try solving without hints to move to Independent stage.",
            "cta": "Practice Without Hints",
            "cta_action": "showProblemBrowser()",
            "topic": topic,
        }

    return {
        "type": "advance",
        "message": "Great mastery across topics! Try harder problems to push toward Mastered stage.",
        "cta": "Try a Hard Problem",
        "cta_action": "showProblemBrowser()",
    }


mastery_engine = CurrentMasteryEngine()

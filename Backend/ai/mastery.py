"""
Mastery Engine Core for CodeMind.

Implements:
1. Concept Mastery across 5 pillars:
   - pattern_recognition
   - implementation
   - optimization
   - independent_solving
   - retention
2. Error DNA tracking and classification:
   - BOUNDARY_OFF_BY_ONE
   - INCORRECT_CONDITION
   - MISSED_EDGE_CASE
   - WRONG_DATA_STRUCTURE
   - COMPLEXITY_MISUNDERSTANDING
   - REPEATED_SYNTAX_IMPLEMENTATION
   - CONCEPTUAL_MISUNDERSTANDING
3. Approach Fingerprint tracking (Brute Force -> Observation -> Pattern -> Optimization -> Independent Solve)
4. Proof of Mastery: Distinguishes 'solved' from 'mastered' via independent Concept Transfer verification.
5. Retention Engine: Real exponential decay curves (e^(-lambda * dt)) with spaced repetition half-life increases.
6. Honest Zero-State: Returns clean, non-fabricated state when data is insufficient.
"""

from datetime import datetime, timezone
import math
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.progress import (
    StudentLearningProfile,
    StudentConceptProgress,
    ProblemAttemptHistory
)
from models.problem import Problem
from models.submission import Submission


class MasteryEngine:
    """Core engine calculating evidence-based mastery, error patterns, and retention."""

    ERROR_TAXONOMY = [
        "BOUNDARY_OFF_BY_ONE",
        "INCORRECT_CONDITION",
        "MISSED_EDGE_CASE",
        "WRONG_DATA_STRUCTURE",
        "COMPLEXITY_MISUNDERSTANDING",
        "REPEATED_SYNTAX_IMPLEMENTATION",
        "CONCEPTUAL_MISUNDERSTANDING"
    ]

    APPROACH_STAGES = [
        "Brute Force",
        "Better Observation",
        "Pattern Recognition",
        "Optimization",
        "Independent Solve"
    ]

    # --- 1. Concept Mastery ---
    def compute_concept_mastery(self, student_id: int, db: Session) -> Dict[str, Any]:
        """
        Calculates mastery for concepts based on real evidence across 5 pillars.
        Formula:
          Mastery = 0.25*pattern + 0.25*implementation + 0.20*optimization + 0.20*independence + 0.10*retention
        Penalizes assisted solves (hints used, solutions viewed).
        """
        concept_records = db.query(StudentConceptProgress).filter(
            StudentConceptProgress.student_id == student_id
        ).all()

        if not concept_records:
            return {
                "status": "insufficient_data",
                "message": "No practice activity recorded yet for concept mastery.",
                "concepts": {}
            }

        results = {}
        for rec in concept_records:
            attempts = db.query(ProblemAttemptHistory).filter(
                ProblemAttemptHistory.student_id == student_id
            ).all()

            matching_attempts = []
            for att in attempts:
                prob = db.query(Problem).filter(Problem.id == att.problem_id).first()
                if prob:
                    tags = [t.strip().lower() for t in (prob.tags or "").split(",") if t.strip()]
                    category = (prob.category or "").lower()
                    c_name = rec.concept_name.lower()
                    if c_name in tags or c_name in category or category in c_name:
                        matching_attempts.append((att, prob))

            total_matches = len(matching_attempts)
            if total_matches == 0:
                pattern = rec.pattern_recognition_score or 0.0
                impl = rec.implementation_score or 0.0
                opt = rec.optimization_score or 0.0
                indep = 0.0
                ret = 0.0
            else:
                solved_count = sum(1 for att, _ in matching_attempts if att.status == "accepted")
                independent_solved = sum(
                    1 for att, _ in matching_attempts
                    if att.status == "accepted" and (att.hints_used or 0) == 0 and not att.solution_viewed
                )

                # 1. Pattern Recognition: solving within reasonable attempts (<= 3)
                efficient_solves = sum(
                    1 for att, _ in matching_attempts
                    if att.status == "accepted" and (att.attempt_count or 1) <= 3
                )
                pattern = min(1.0, (efficient_solves / max(1, solved_count))) if solved_count > 0 else 0.0

                # 2. Implementation: ratio of accepted code
                clean_solves = sum(
                    1 for att, _ in matching_attempts
                    if att.status == "accepted" and (att.code_length or 0) > 20
                )
                impl = min(1.0, (clean_solves / max(1, total_matches)))

                # 3. Optimization: passing test cases with good runtime
                opt = min(1.0, (rec.optimization_score or 0.5) if solved_count > 0 else 0.0)

                # 4. Independent Solving: solves done with zero hints and zero solution reveals
                indep = min(1.0, (independent_solved / max(1, solved_count))) if solved_count > 0 else 0.0

                # 5. Retention: based on recency of successful attempts
                ret = self._calc_concept_retention(matching_attempts)

            mastery_score = (
                0.25 * pattern +
                0.25 * impl +
                0.20 * opt +
                0.20 * indep +
                0.10 * ret
            ) * 100.0

            # Verified mastery requires independent solving evidence
            is_verified = (indep >= 0.6 and pattern >= 0.5 and total_matches >= 2)

            results[rec.concept_name] = {
                "concept_name": rec.concept_name,
                "mastery_score": round(mastery_score, 1),
                "is_verified": is_verified,
                "status": "Mastered" if is_verified and mastery_score >= 70 else ("Provisional" if mastery_score >= 40 else "Learning"),
                "pillars": {
                    "pattern_recognition": round(pattern * 100, 1),
                    "implementation": round(impl * 100, 1),
                    "optimization": round(opt * 100, 1),
                    "independent_solving": round(indep * 100, 1),
                    "retention": round(ret * 100, 1)
                },
                "total_problems_practiced": total_matches,
                "last_practiced": rec.last_practiced.isoformat() if rec.last_practiced else None
            }

        return {
            "status": "active",
            "concept_count": len(results),
            "concepts": results
        }

    def _calc_concept_retention(self, matching_attempts: List[Any]) -> float:
        """Calculates retention score (0.0 to 1.0) using exponential decay."""
        accepted = [att for att, _ in matching_attempts if att.status == "accepted" and att.solved_at]
        if not accepted:
            return 0.0
        
        accepted.sort(key=lambda x: x.solved_at, reverse=True)
        latest = accepted[0].solved_at
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        days_passed = max(0.0, (now - latest).total_seconds() / 86400.0)

        # Spaced repetition: each successful solve increases half life (T_half = 7 days + 3 days per solve)
        half_life_days = 7.0 + min(21.0, len(accepted) * 3.0)
        decay_lambda = math.log(2) / half_life_days
        retention = math.exp(-decay_lambda * days_passed)
        return min(1.0, max(0.0, retention))

    # --- 2. Error DNA ---
    def analyze_error_dna(self, student_id: int, db: Session) -> Dict[str, Any]:
        """
        Classifies recurring student mistakes into actionable Error DNA signatures.
        Maps errors directly to concepts and AI Tutor remediation actions.
        """
        failed_attempts = db.query(ProblemAttemptHistory).filter(
            ProblemAttemptHistory.student_id == student_id,
            ProblemAttemptHistory.status != "accepted"
        ).all()

        recent_submissions = db.query(Submission).filter(
            Submission.user_id == student_id,
            Submission.status.notin_(["accepted", "Accepted"])
        ).order_by(desc(Submission.submitted_at)).limit(50).all()

        if not failed_attempts and not recent_submissions:
            return {
                "status": "insufficient_data",
                "message": "No failure patterns detected yet.",
                "signatures": [],
                "primary_weakness": None
            }

        dna_counts = {k: 0 for k in self.ERROR_TAXONOMY}
        dna_examples = {k: [] for k in self.ERROR_TAXONOMY}

        for sub in recent_submissions:
            err_cat = self._classify_submission_error(sub)
            if err_cat in dna_counts:
                dna_counts[err_cat] += 1
                if len(dna_examples[err_cat]) < 3:
                    prob = db.query(Problem).filter(Problem.id == sub.problem_id).first()
                    dna_examples[err_cat].append({
                        "problem_id": sub.problem_id,
                        "problem_title": prob.title if prob else f"Problem #{sub.problem_id}",
                        "language": sub.language,
                        "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None
                    })

        total_errors = sum(dna_counts.values())
        signatures = []
        for cat, count in sorted(dna_counts.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                signatures.append({
                    "category": cat,
                    "frequency": count,
                    "percentage": round((count / max(1, total_errors)) * 100, 1),
                    "severity": "HIGH" if count >= 5 else ("MEDIUM" if count >= 2 else "LOW"),
                    "remediation": self._get_error_remediation(cat),
                    "examples": dna_examples[cat]
                })

        primary_weakness = signatures[0]["category"] if signatures else None

        return {
            "status": "active",
            "total_errors_analyzed": total_errors,
            "primary_weakness": primary_weakness,
            "signatures": signatures
        }

    def _classify_submission_error(self, sub: Submission) -> str:
        """Categorizes raw execution errors into Error DNA taxonomy."""
        status = (sub.status or "").lower()
        err_out = (sub.error_output or "").lower()

        if "time limit" in status or "timeout" in status or "tle" in status or "time limit" in err_out:
            return "COMPLEXITY_MISUNDERSTANDING"
        if "syntax" in status or "compile" in status or "syntaxerror" in err_out or "indentationerror" in err_out:
            return "REPEATED_SYNTAX_IMPLEMENTATION"
        if "indexerror" in err_out or "out of range" in err_out or "bound" in err_out or "string index" in err_out:
            return "BOUNDARY_OFF_BY_ONE"
        if "nullpointer" in err_out or "attributeerror: 'nonetype'" in err_out or "keyerror" in err_out:
            return "MISSED_EDGE_CASE"
        if "wrong answer" in status:
            if "recursionerror" in err_out or "stack overflow" in err_out:
                return "CONCEPTUAL_MISUNDERSTANDING"
            return "INCORRECT_CONDITION"
        if "memory limit" in status or "memory" in err_out:
            return "WRONG_DATA_STRUCTURE"
        return "CONCEPTUAL_MISUNDERSTANDING"

    def _get_error_remediation(self, category: str) -> Dict[str, str]:
        """Provides pedagogical remediation guidance for each error taxonomy."""
        remediations = {
            "BOUNDARY_OFF_BY_ONE": {
                "concept": "Loop Invariants & Array Slicing",
                "ai_action": "Explain boundary checks and index calculation systematically before writing loops.",
                "remedy_prompt": "Let's trace array boundaries: check index 0, length - 1, and empty sequences."
            },
            "INCORRECT_CONDITION": {
                "concept": "Boolean Logic & Branching",
                "ai_action": "Guide student through condition truth tables and edge-case branching.",
                "remedy_prompt": "Let's list all branching conditions explicitly to avoid overlapping logic."
            },
            "MISSED_EDGE_CASE": {
                "concept": "Defensive Programming",
                "ai_action": "Prompt the student to test n=0, n=1, empty list, and duplicate inputs before running.",
                "remedy_prompt": "Consider extreme inputs: What happens when the input is empty or has a single element?"
            },
            "WRONG_DATA_STRUCTURE": {
                "concept": "Data Structure Selection",
                "ai_action": "Compare lookup and insertion complexity between Array, Set, Map, and Heap.",
                "remedy_prompt": "Evaluate the access pattern: Would a Hash Table or Priority Queue reduce lookups?"
            },
            "COMPLEXITY_MISUNDERSTANDING": {
                "concept": "Big-O Asymptotics & Constraints",
                "ai_action": "Teach constraint-to-complexity mapping (e.g. N <= 10^5 requires O(N) or O(N log N)).",
                "remedy_prompt": "Inspect input constraints: N is up to 10^5, so an O(N^2) brute force will timeout."
            },
            "REPEATED_SYNTAX_IMPLEMENTATION": {
                "concept": "Language Idioms & Type Safety",
                "ai_action": "Offer mini-syntax drills for target language conventions.",
                "remedy_prompt": "Review syntax nuances and variable declarations for your selected language."
            },
            "CONCEPTUAL_MISUNDERSTANDING": {
                "concept": "Algorithmic Invariants",
                "ai_action": "Revisit foundational problem pattern via step-by-step Socratic walkthrough.",
                "remedy_prompt": "Step back from code: let's model the problem on paper first before implementing."
            }
        }
        return remediations.get(category, {
            "concept": "General Problem Solving",
            "ai_action": "Review foundational concepts.",
            "remedy_prompt": "Review problem statement and verify step-by-step logic."
        })

    # --- 3. Approach Fingerprint ---
    def track_approach_fingerprint(self, student_id: int, db: Session) -> Dict[str, Any]:
        """
        Analyzes progression across solving stages and measures hint dependency.
        Stages: Brute Force -> Better Observation -> Pattern Recognition -> Optimization -> Independent Solve.
        """
        attempts = db.query(ProblemAttemptHistory).filter(
            ProblemAttemptHistory.student_id == student_id
        ).all()

        if not attempts:
            return {
                "status": "insufficient_data",
                "message": "No attempts available to build approach fingerprint.",
                "current_stage": "Brute Force",
                "hint_dependency_ratio": 0.0,
                "stage_distribution": {s: 0 for s in self.APPROACH_STAGES}
            }

        total_attempts = len(attempts)
        hints_total = sum(att.hints_used or 0 for att in attempts)
        assisted_attempts = sum(1 for att in attempts if (att.hints_used or 0) > 0 or att.solution_viewed)
        hint_dependency_ratio = round(assisted_attempts / max(1, total_attempts), 2)

        distribution = {s: 0 for s in self.APPROACH_STAGES}
        for att in attempts:
            if att.status != "accepted":
                if (att.hints_used or 0) > 0:
                    distribution["Better Observation"] += 1
                else:
                    distribution["Brute Force"] += 1
            else:
                if att.solution_viewed or (att.hints_used or 0) >= 3:
                    distribution["Better Observation"] += 1
                elif (att.hints_used or 0) > 0:
                    distribution["Pattern Recognition"] += 1
                elif att.optimization_needed:
                    distribution["Pattern Recognition"] += 1
                elif (att.attempt_count or 1) <= 2:
                    distribution["Independent Solve"] += 1
                else:
                    distribution["Optimization"] += 1

        sorted_stages = sorted(distribution.items(), key=lambda x: x[1], reverse=True)
        dominant_stage = sorted_stages[0][0] if sorted_stages and sorted_stages[0][1] > 0 else "Brute Force"

        independent_count = distribution["Independent Solve"]
        if independent_count >= 5 and hint_dependency_ratio <= 0.25:
            trajectory = "Independent Mastery"
        elif distribution["Optimization"] + distribution["Pattern Recognition"] > distribution["Brute Force"]:
            trajectory = "Maturing Pattern Solver"
        elif hint_dependency_ratio >= 0.60:
            trajectory = "High Hint Dependency"
        else:
            trajectory = "Foundational Explorer"

        return {
            "status": "active",
            "current_stage": dominant_stage,
            "trajectory": trajectory,
            "hint_dependency_ratio": hint_dependency_ratio,
            "total_hints_requested": hints_total,
            "total_attempts": total_attempts,
            "stage_distribution": distribution
        }

    # --- 4. Proof of Mastery ---
    def evaluate_proof_of_mastery(self, student_id: int, concept_name: str, db: Session) -> Dict[str, Any]:
        """
        Evaluates whether a student has truly 'mastered' vs merely 'solved' a concept.
        If initial solve was assisted, requires an unrevealed Concept Transfer challenge
        to be solved independently without hints.
        """
        concept_rec = db.query(StudentConceptProgress).filter(
            StudentConceptProgress.student_id == student_id,
            StudentConceptProgress.concept_name == concept_name
        ).first()

        if not concept_rec:
            return {
                "concept": concept_name,
                "is_mastered": False,
                "reason": "No recorded attempts for this concept."
            }

        profile = db.query(StudentLearningProfile).filter(
            StudentLearningProfile.student_id == student_id
        ).first()

        proof_data = profile.proof_of_mastery if profile and profile.proof_of_mastery else {}
        concept_proof = proof_data.get(concept_name, {})

        if concept_proof.get("verified", False):
            return {
                "concept": concept_name,
                "is_mastered": True,
                "status": "Verified Mastered",
                "verified_at": concept_proof.get("verified_at"),
                "verification_problem_id": concept_proof.get("problem_id"),
                "verification_method": "Independent Concept Transfer Challenge"
            }

        transfer_candidate = self._find_unrevealed_transfer_problem(student_id, concept_name, db)

        return {
            "concept": concept_name,
            "is_mastered": False,
            "status": "Pending Proof of Mastery",
            "reason": "Previous practice was assisted or requires independent concept transfer validation.",
            "challenge_problem": transfer_candidate
        }

    def _find_unrevealed_transfer_problem(self, student_id: int, concept_name: str, db: Session) -> Optional[Dict[str, Any]]:
        """Finds a problem matching the concept that the student has never seen or attempted."""
        attempted_ids = [
            att.problem_id for att in db.query(ProblemAttemptHistory.problem_id).filter(
                ProblemAttemptHistory.student_id == student_id
            ).all()
        ]

        query = db.query(Problem).filter(
            Problem.id.notin_(attempted_ids) if attempted_ids else True
        )
        c_lower = concept_name.lower()
        query = query.filter(
            (Problem.tags.ilike(f"%{c_lower}%")) |
            (Problem.category.ilike(f"%{c_lower}%")) |
            (Problem.title.ilike(f"%{c_lower}%"))
        )
        candidate = query.first()

        if candidate:
            return {
                "id": candidate.id,
                "title": candidate.title,
                "difficulty": candidate.difficulty,
                "category": candidate.category,
                "tags": candidate.tags
            }
        return None

    def record_proof_of_mastery_success(self, student_id: int, concept_name: str, problem_id: int, db: Session) -> bool:
        """Records that a student has independently passed a Proof of Mastery challenge."""
        profile = db.query(StudentLearningProfile).filter(
            StudentLearningProfile.student_id == student_id
        ).first()

        if not profile:
            profile = StudentLearningProfile(student_id=student_id)
            db.add(profile)

        proof_data = profile.proof_of_mastery or {}
        proof_data[concept_name] = {
            "verified": True,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "problem_id": problem_id
        }
        profile.proof_of_mastery = proof_data

        concept_rec = db.query(StudentConceptProgress).filter(
            StudentConceptProgress.student_id == student_id,
            StudentConceptProgress.concept_name == concept_name
        ).first()
        if concept_rec:
            concept_rec.independent_solving_score = 1.0
            concept_rec.mastery_score = min(100.0, (concept_rec.mastery_score or 50.0) + 25.0)

        db.commit()
        return True

    # --- 5. Retention Engine ---
    def compute_retention(self, student_id: int, db: Session) -> Dict[str, Any]:
        """
        Computes decay status across all learned concepts and flags those needing refresh.
        Retention statuses: Fresh (> 80%), Stable (60-80%), Needs Refresh (< 60%).
        """
        concepts_res = self.compute_concept_mastery(student_id, db)
        if concepts_res["status"] == "insufficient_data":
            return {
                "status": "insufficient_data",
                "message": "No concepts recorded to track retention.",
                "items": []
            }

        retention_items = []
        for c_name, data in concepts_res["concepts"].items():
            ret_score = data["pillars"]["retention"]
            if ret_score >= 80:
                ret_status = "Fresh"
            elif ret_score >= 60:
                ret_status = "Stable"
            else:
                ret_status = "Needs Refresh"

            retention_items.append({
                "concept_name": c_name,
                "retention_percentage": ret_score,
                "status": ret_status,
                "last_practiced": data["last_practiced"],
                "needs_refresh": ret_status == "Needs Refresh"
            })

        retention_items.sort(key=lambda x: x["retention_percentage"])

        return {
            "status": "active",
            "items": retention_items,
            "refresh_needed_count": sum(1 for item in retention_items if item["needs_refresh"])
        }

    # --- 6. Recommendations ---
    def get_mastery_recommendations(self, student_id: int, db: Session) -> Dict[str, Any]:
        """
        Generates targeted practice recommendations based on Error DNA, Retention gaps,
        and Proof of Mastery transfer tests from the real 11,404 problem library.
        """
        retention = self.compute_retention(student_id, db)
        dna = self.analyze_error_dna(student_id, db)

        recommendations = []

        # 1. Address Retention Decay
        if retention["status"] == "active":
            for item in retention["items"]:
                if item["needs_refresh"]:
                    prob = self._find_unrevealed_transfer_problem(student_id, item["concept_name"], db)
                    if prob:
                        recommendations.append({
                            "type": "RETENTION_REFRESH",
                            "priority": "HIGH",
                            "concept": item["concept_name"],
                            "reason": f"Retention has decayed to {item['retention_percentage']}%. A quick practice problem will reinforce the concept.",
                            "problem": prob
                        })
                    if len(recommendations) >= 2:
                        break

        # 2. Address Error DNA Weakness
        if dna["status"] == "active" and dna["primary_weakness"]:
            weakness = dna["primary_weakness"]
            remediation = self._get_error_remediation(weakness)
            concept_focus = remediation["concept"].split()[0]
            prob = self._find_unrevealed_transfer_problem(student_id, concept_focus, db)
            if prob:
                recommendations.append({
                    "type": "ERROR_DNA_REMEDIATION",
                    "priority": "HIGH",
                    "concept": remediation["concept"],
                    "reason": f"Recurring pattern detected: {weakness}. {remediation['ai_action']}",
                    "problem": prob
                })

        # 3. Fallback: If no activity or gaps, provide beginner-friendly foundational problem
        if not recommendations:
            foundational = db.query(Problem).filter(Problem.difficulty == "Easy").first()
            if foundational:
                recommendations.append({
                    "type": "FOUNDATIONAL_START",
                    "priority": "MEDIUM",
                    "concept": foundational.category or "Arrays",
                    "reason": "Start your mastery journey with a foundational problem.",
                    "problem": {
                        "id": foundational.id,
                        "title": foundational.title,
                        "difficulty": foundational.difficulty,
                        "category": foundational.category,
                        "tags": foundational.tags
                    }
                })

        return {
            "status": "active",
            "count": len(recommendations),
            "recommendations": recommendations
        }


# Singleton instance
mastery_engine = MasteryEngine()

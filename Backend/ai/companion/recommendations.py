import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_

from models import Problem, ProblemSubmission, Tag

logger = logging.getLogger("codemind.companion.recommendations")

TOPIC_KEYWORD_MAP: Dict[str, List[str]] = {
    "stack": ["stack", "parentheses", "monotonic"],
    "queue": ["queue", "bfs", "breadth"],
    "linked list": ["linked-list", "linkedlist", "list", "node"],
    "two pointers": ["two-pointer", "two-pointers", "pointer", "sliding-window", "palindrome"],
    "array": ["array", "prefix-sum", "matrix"],
    "sorting": ["sort", "sorting", "merge", "bubble"],
    "recursion": ["recursion", "backtracking", "recursive", "dfs"],
    "tree": ["tree", "binary-tree", "bst", "traversal"],
    "trees": ["tree", "binary-tree", "bst", "traversal"],
    "graph": ["graph", "bfs", "dfs", "topological"],
    "graphs": ["graph", "bfs", "dfs", "topological"],
    "pointers": ["pointer", "memory", "linked-list", "array"],
    "binary search": ["binary-search", "search", "divide-and-conquer"],
    "searching": ["binary-search", "search"],
    "hash table": ["hash-table", "hash", "map", "dictionary"],
    "dynamic programming": ["dynamic-programming", "dp", "memoization"]
}

def get_companion_recommendations(
    student_id: str,
    db: Session,
    topic: Optional[str] = None,
    current_problem_id: Optional[str] = None,
    last_error: Optional[str] = None,
    current_difficulty: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Builds personalized, progressive problem recommendations using real CodeMind
    database problems and real student submission/mastery history.
    
    Tiers generated:
    1. Easier Practice (Foundational reinforcement on the topic)
    2. Similar Difficulty (Peer-level application of the concept)
    3. Step-Up Challenge (Deeper challenge or error recovery)
    """
    if not db:
        return []

    try:
        # 1. Fetch real student submissions to filter solved/attempted problems
        submissions = (
            db.query(ProblemSubmission)
            .filter(ProblemSubmission.student_id == student_id)
            .all()
        )
        solved_ids = {s.problem_id for s in submissions if (s.status or "").lower() == "accepted"}
        attempted_ids = {s.problem_id for s in submissions}

        excluded_ids = set(solved_ids)
        if current_problem_id:
            excluded_ids.add(current_problem_id)

        # 2. Determine target topic
        target_topic = (topic or "").strip()
        if not target_topic and current_problem_id:
            # Fall back to active problem title/tags
            active_p = db.query(Problem).filter(Problem.id == current_problem_id).first()
            if active_p:
                if active_p.tags:
                    target_topic = active_p.tags[0].name
                else:
                    target_topic = active_p.title or "General Practice"

        if not target_topic:
            target_topic = "Array"

        topic_lower = target_topic.lower()
        search_keywords = TOPIC_KEYWORD_MAP.get(topic_lower, [topic_lower.replace(" ", "-"), topic_lower])

        # 3. Progressive query helper
        def query_problems(difficulty_filter: Optional[str], limit: int = 5) -> List[Problem]:
            # Build search conditions across Problem.title and Tag.name
            tag_conds = [Problem.tags.any(Tag.name.ilike(f"%{kw}%")) for kw in search_keywords]
            title_conds = [Problem.title.ilike(f"%{kw}%") for kw in search_keywords]
            topic_filter = or_(*tag_conds, *title_conds)

            q = db.query(Problem).filter(
                Problem.is_active == True,
                ~Problem.id.in_(excluded_ids)
            )

            if difficulty_filter:
                q = q.filter(Problem.difficulty == difficulty_filter)

            # First attempt topic filter
            results = q.filter(topic_filter).limit(limit).all()
            if not results:
                # If no direct match with topic, fallback to matching by difficulty
                results = q.limit(limit).all()
            return results

        recommendations: List[Dict[str, Any]] = []
        seen_problem_ids: set = set(excluded_ids)

        # Tier 1: Foundational / Easier Practice
        easy_candidates = query_problems("Easy", limit=6)
        easy_pick = next((p for p in easy_candidates if p.id not in seen_problem_ids), None)
        if easy_pick:
            seen_problem_ids.add(easy_pick.id)
            if last_error:
                reason = f"🎯 Foundational Practice: Solidify {target_topic} mechanics without edge case overhead."
            else:
                reason = f"🎯 Foundational Practice: Build immediate confidence and intuition with {target_topic}."
            recommendations.append({
                "problem_id": easy_pick.id,
                "title": easy_pick.title,
                "difficulty": easy_pick.difficulty or "Easy",
                "topic": target_topic,
                "reason": reason,
                "tier": "easier"
            })

        # Tier 2: Peer / Similar Challenge
        target_similar_diff = current_difficulty if current_difficulty in ["Easy", "Medium", "Hard"] else "Medium"
        similar_candidates = query_problems(target_similar_diff, limit=6)
        similar_pick = next((p for p in similar_candidates if p.id not in seen_problem_ids), None)
        if similar_pick:
            seen_problem_ids.add(similar_pick.id)
            if last_error:
                reason = f"🔄 Error Recovery: Apply clean boundary checks and logic patterns to a fresh {target_similar_diff} challenge."
            else:
                reason = f"💡 Similar Practice: Reinforce this exact algorithmic approach on an unsolved problem."
            recommendations.append({
                "problem_id": similar_pick.id,
                "title": similar_pick.title,
                "difficulty": similar_pick.difficulty or target_similar_diff,
                "topic": target_topic,
                "reason": reason,
                "tier": "similar"
            })

        # Tier 3: Step-Up / Harder Challenge
        challenge_diff = "Hard" if target_similar_diff != "Hard" else "Hard"
        hard_candidates = query_problems(challenge_diff, limit=6)
        if not hard_candidates and challenge_diff == "Hard":
            hard_candidates = query_problems("Medium", limit=6)
        hard_pick = next((p for p in hard_candidates if p.id not in seen_problem_ids), None)
        if hard_pick:
            seen_problem_ids.add(hard_pick.id)
            reason = f"🚀 Step-Up Challenge: Test your mastery with complex constraints and optimizations."
            recommendations.append({
                "problem_id": hard_pick.id,
                "title": hard_pick.title,
                "difficulty": hard_pick.difficulty or "Medium",
                "topic": target_topic,
                "reason": reason,
                "tier": "challenge"
            })

        # Fallback if fewer than 2 recommendations were populated
        if len(recommendations) < 2:
            generic_candidates = (
                db.query(Problem)
                .filter(Problem.is_active == True, ~Problem.id.in_(seen_problem_ids))
                .limit(3)
                .all()
            )
            for p in generic_candidates:
                if len(recommendations) >= 3:
                    break
                seen_problem_ids.add(p.id)
                recommendations.append({
                    "problem_id": p.id,
                    "title": p.title,
                    "difficulty": p.difficulty or "Medium",
                    "topic": target_topic,
                    "reason": f"📌 Curated Practice: Expand your problem-solving repertoire in CodeMind.",
                    "tier": "similar"
                })

        return recommendations

    except Exception as e:
        logger.error("Error generating companion recommendations: %s", e)
        return []

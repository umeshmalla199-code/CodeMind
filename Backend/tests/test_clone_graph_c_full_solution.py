import pytest
from unittest.mock import patch
from db.session import SessionLocal
from routes.ai import run_full_solution_pipeline, solution_cache, _build_c_clone_graph_executable, _is_clone_graph_c
from execution import execute_code
from models import Problem

def test_clone_graph_c_contract_in_database():
    """Verify that clone-undirected-graph in DB has the C starter code with struct Node and cloneGraph."""
    db = SessionLocal()
    try:
        p = db.query(Problem).filter(Problem.id == "clone-undirected-graph").first()
        assert p is not None, "Problem clone-undirected-graph not found in database"
        assert isinstance(p.starter_code, dict)
        assert "c" in p.starter_code, "C starter code missing from problem"
        c_code = p.starter_code["c"]
        assert "struct Node" in c_code
        assert "cloneGraph" in c_code
        assert "c" in p.supported_languages
    finally:
        db.close()

def test_c_clone_graph_harness_accepts_valid_deep_copy():
    """Verify that the C test harness accepts a mathematically correct deep copy solution."""
    valid_c = """#include <stdio.h>
#include <stdlib.h>
struct Node { int val; int numNeighbors; struct Node** neighbors; };
static struct Node* visited[105];
struct Node* cloneGraph(struct Node* node) {
    if (!node) return NULL;
    if (visited[node->val]) return visited[node->val];
    struct Node* clone = (struct Node*)malloc(sizeof(struct Node));
    clone->val = node->val;
    clone->numNeighbors = node->numNeighbors;
    clone->neighbors = (struct Node**)malloc(sizeof(struct Node*) * (node->numNeighbors > 0 ? node->numNeighbors : 1));
    visited[node->val] = clone;
    for (int i = 0; i < node->numNeighbors; i++) {
        clone->neighbors[i] = cloneGraph(node->neighbors[i]);
    }
    return clone;
}
"""
    exe_c = _build_c_clone_graph_executable(valid_c)
    res = execute_code(
        language="c",
        source_code=exe_c,
        test_cases=[{"input": "adjList = [[2,4],[1,3],[2,4],[1,3]]", "output": "[[2,4],[1,3],[2,4],[1,3]]"}]
    )
    assert res.get("status") == "accepted"
    assert res.get("passed_count") == 1

def test_c_clone_graph_harness_rejects_shallow_copy():
    """Negative test: verify that returning the input node (shallow copy) fails with runtime_error."""
    shallow_c = """#include <stdio.h>
struct Node { int val; int numNeighbors; struct Node** neighbors; };
struct Node* cloneGraph(struct Node* node) {
    return node;
}
"""
    exe_c = _build_c_clone_graph_executable(shallow_c)
    res = execute_code(
        language="c",
        source_code=exe_c,
        test_cases=[{"input": "adjList = [[2,4],[1,3],[2,4],[1,3]]", "output": "[[2,4],[1,3],[2,4],[1,3]]"}]
    )
    assert res.get("status") == "runtime_error"
    assert "shallow copy" in (res.get("error") or res.get("stderr") or "")
    assert res.get("passed_count") == 0

def test_full_solution_pipeline_end_to_end_clone_graph_c():
    """End-to-end verification: Full Solution pipeline verifies the C clone graph solution."""
    solution_cache.invalidate()
    db = SessionLocal()
    try:
        res = run_full_solution_pipeline(
            problem_id="clone-undirected-graph",
            language="c",
            db=db,
        )
        assert res.get("validation_status") == "verified"
        assert res.get("validation_passed") is True
        assert res.get("passed_count") == 1
        assert "Verified: Passed 1/1 test cases" in res.get("validation_label", "")
        assert "Verified by CodeMind Execution Runner" in res.get("formatted_text", "")
    finally:
        db.close()

def test_full_solution_pipeline_negative_gate():
    """Negative gate: If repair fails to produce working code, the system never claims verified."""
    solution_cache.invalidate()
    db = SessionLocal()
    try:
        with patch("routes.ai.AITutorEngine.generate_full_solution") as mock_gen:
            mock_gen.return_value = {
                "code": "struct Node* cloneGraph(struct Node* node) { return node; }",
                "understanding": "...", "key_observation": "...", "approach": "...",
                "why_it_works": "...", "complexity": "O(N)", "test_check": "..."
            }
            res = run_full_solution_pipeline(
                problem_id="clone-undirected-graph",
                language="c",
                db=db,
            )
            assert res.get("validation_passed") is False
            assert res.get("validation_status") == "runtime_error"
            assert "Verified by CodeMind Execution Runner" not in res.get("formatted_text", "")
            assert "cannot honestly claim" in res.get("formatted_text", "")
    finally:
        db.close()

"""
CodeMind Repair Verification Tests (Prompt 6)
==============================================
Tests the specific root-cause fixes applied in this session:

1. DEQUE simulator — correct structure, correct renderer dispatch
2. Intent resolution — "double ended queue" → deque (NOT queue)
3. Auth token security — no tokens in API responses
4. Auth privilege escalation — "founder" username no longer grants founder role
5. Password change — session revocation works
6. Viz stale prevention — viz_request_id in schema
7. Schemas — conversation_id, request_id in CompanionChatRequest
8. Email dispatch infrastructure — SMTP config detection, dev fallback logging

Run with:
    Backend\\venv\\Scripts\\python.exe -m pytest Backend/tests/test_repair_prompt6.py -v --tb=short
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import importlib


# =====================================================================
# 1. DEQUE INTENT RESOLUTION
# =====================================================================
class TestDequeIntentResolution:
    """'double ended queue' and 'deque' must resolve to deque, NOT queue."""

    def _extract(self, msg: str):
        from ai.companion.viz_simulator import extract_visualization_plan
        return extract_visualization_plan(msg, None, None)

    def test_deque_keyword_resolves_to_deque(self):
        plan = self._extract("show me a deque")
        assert plan is not None, "Should return a plan for 'deque'"
        assert plan.structure == "deque", f"Expected 'deque', got '{plan.structure}'"

    def test_double_ended_queue_resolves_to_deque(self):
        plan = self._extract("visualize double ended queue with values 10 20 30")
        assert plan is not None
        assert plan.structure == "deque", f"Expected 'deque', got '{plan.structure}'"

    def test_double_ended_queue_with_hyphen_resolves_to_deque(self):
        plan = self._extract("double-ended queue insert 5")
        assert plan is not None
        assert plan.structure == "deque"

    def test_pushfront_resolves_to_deque(self):
        plan = self._extract("pushFront 42 into deque")
        assert plan is not None
        assert plan.structure == "deque"
        assert plan.operation in ("pushfront", "pushFront")

    def test_popfront_resolves_to_deque(self):
        plan = self._extract("popFront from deque with 10 20")
        assert plan is not None
        assert plan.structure == "deque"
        assert plan.operation in ("popfront", "popFront")

    def test_regular_queue_still_works(self):
        """Normal 'queue' should still resolve to queue, not deque."""
        plan = self._extract("show me enqueue and dequeue operations on a queue")
        assert plan is not None
        assert plan.structure == "queue", f"Expected 'queue', got '{plan.structure}'"

    def test_circular_queue_still_works(self):
        plan = self._extract("visualize circular queue with 5 elements")
        assert plan is not None
        assert plan.structure == "circular_queue", f"Expected 'circular_queue', got '{plan.structure}'"


# =====================================================================
# 2. DEQUE SIMULATOR — DeterministicSimulator._simulate_deque()
# =====================================================================
class TestDequeSimulator:
    """DeterministicSimulator must produce correct deque VisualizationSpec."""

    def _simulate(self, initial, op="push_pop_both_ends", target=30):
        from ai.companion.viz_simulator import DeterministicSimulator, VisualizationPlan
        plan = VisualizationPlan(
            structure="deque",
            operation=op,
            initial_values=initial,
            target_value=target
        )
        return DeterministicSimulator.simulate(plan)

    def test_deque_returns_viz_spec(self):
        spec = self._simulate([10, 20])
        assert spec is not None, "Deque simulator should return a VisualizationSpec"

    def test_deque_viz_type_is_deque(self):
        spec = self._simulate([10, 20])
        assert spec.viz_type == "deque", f"Expected viz_type='deque', got '{spec.viz_type}'"

    def test_deque_has_steps(self):
        spec = self._simulate([10, 20])
        assert len(spec.steps) > 0, "Deque simulator should produce steps"

    def test_deque_pushfront_operation(self):
        spec = self._simulate([10, 20], op="pushFront", target=5)
        assert spec is not None
        push_steps = [s for s in spec.steps if s.action == "pushFront"]
        assert len(push_steps) > 0, "pushFront operation should produce pushFront step"
        assert push_steps[0].value == 5

    def test_deque_pushrear_operation(self):
        spec = self._simulate([10, 20], op="pushRear", target=99)
        push_steps = [s for s in spec.steps if s.action == "pushRear"]
        assert len(push_steps) > 0
        assert push_steps[0].value == 99

    def test_deque_popfront_operation(self):
        spec = self._simulate([10, 20, 30], op="popFront")
        pop_steps = [s for s in spec.steps if s.action == "popFront"]
        assert len(pop_steps) > 0
        assert pop_steps[0].value == 10  # First element should be popped

    def test_deque_poprear_operation(self):
        spec = self._simulate([10, 20, 30], op="popRear")
        pop_steps = [s for s in spec.steps if s.action == "popRear"]
        assert len(pop_steps) > 0
        assert pop_steps[0].value == 30  # Last element should be popped

    def test_deque_combined_demo_has_both_push_pop_steps(self):
        spec = self._simulate([10, 20], op="push_pop_both_ends", target=30)
        actions = {s.action for s in spec.steps}
        assert "pushFront" in actions, f"Combined demo should have pushFront. Got: {actions}"
        assert "pushRear" in actions, f"Combined demo should have pushRear. Got: {actions}"
        assert "popFront" in actions, f"Combined demo should have popFront. Got: {actions}"
        assert "popRear" in actions, f"Combined demo should have popRear. Got: {actions}"

    def test_deque_not_same_as_queue(self):
        """Deque simulator should be separate from queue — deque explanation must differentiate."""
        spec = self._simulate([10, 20])
        explanations = " ".join(s.explanation for s in spec.steps)
        assert "deque" in explanations.lower() or "double" in explanations.lower() or "both end" in explanations.lower(), \
            "Deque simulator should explain deque concept"

    def test_deque_simulate_returns_not_none_for_all_ops(self):
        for op in ["pushFront", "pushRear", "popFront", "popRear", "push_pop_both_ends"]:
            spec = self._simulate([10, 20], op=op, target=5)
            assert spec is not None, f"Deque simulator returned None for op={op}"
            assert spec.viz_type == "deque"


# =====================================================================
# 3. AUTH SECURITY — No tokens in API responses
# =====================================================================
class TestAuthTokenSecurity:
    """Auth endpoints must NOT return sensitive tokens in response bodies."""

    def test_register_response_has_no_verification_token_key(self):
        """The register endpoint handler should not include verification_token in return dict."""
        import inspect
        from routes.auth import register  # type: ignore
        source = inspect.getsource(register)
        # The field should NOT be in the return dict
        assert '"verification_token": verification_token' not in source, \
            "register() should not return verification_token in response"
        assert 'verification_token' not in source.split('return {')[1].split('}')[0] if 'return {' in source else True, \
            "register() should not include verification_token in return dict"

    def test_forgot_password_response_has_no_reset_token_key(self):
        """The forgot_password handler must not include reset_token in return dict."""
        import inspect
        from routes.auth import forgot_password  # type: ignore
        source = inspect.getsource(forgot_password)
        return_section = source.split('return {')[-1] if 'return {' in source else ''
        assert '"reset_token"' not in return_section or 'reset_token' not in return_section, \
            "forgot_password() should not return reset_token in response"

    def test_resend_verification_no_token_in_response(self):
        """resend_verification must not include verification_token in return."""
        import inspect
        # Find the resend-verification function
        import routes.auth as auth_routes
        # Look at the full module source for the return in resend function
        full_source = inspect.getsource(auth_routes)
        # After we patched it, the return after resend_verification should not have the token
        assert '"verification_token": new_token' not in full_source, \
            "resend_verification should not return verification_token in response"

    def test_dispatch_verification_email_function_exists(self):
        """Email dispatch helper must exist in routes.auth."""
        from routes import auth as auth_routes
        assert hasattr(auth_routes, '_dispatch_verification_email'), \
            "_dispatch_verification_email() function should exist"

    def test_dispatch_password_reset_email_function_exists(self):
        """Password reset email dispatch helper must exist."""
        from routes import auth as auth_routes
        assert hasattr(auth_routes, '_dispatch_password_reset_email'), \
            "_dispatch_password_reset_email() function should exist"

    def test_smtp_email_function_exists(self):
        """SMTP email send function must exist."""
        from routes import auth as auth_routes
        assert hasattr(auth_routes, '_send_smtp_email'), "_send_smtp_email() should exist"

    def test_smtp_returns_false_without_config(self):
        """Without SMTP env vars, _send_smtp_email must return False (not raise)."""
        # Temporarily clear SMTP config
        old_host = os.environ.pop('SMTP_HOST', None)
        try:
            from routes.auth import _send_smtp_email
            result = _send_smtp_email("test@example.com", "Test", "<p>html</p>", "text")
            assert result is False, "Should return False when SMTP not configured"
        finally:
            if old_host:
                os.environ['SMTP_HOST'] = old_host

    def test_verify_email_link_endpoint_exists(self):
        """GET /api/auth/verify-email-link endpoint must exist."""
        from routes import auth as auth_routes
        route_paths = [r.path for r in auth_routes.router.routes]
        assert any('verify-email-link' in p for p in route_paths), \
            f"verify-email-link route should exist. Found: {route_paths}"

    def test_reset_password_link_endpoint_exists(self):
        """GET /api/auth/reset-password-link endpoint must exist."""
        from routes import auth as auth_routes
        route_paths = [r.path for r in auth_routes.router.routes]
        assert any('reset-password-link' in p for p in route_paths), \
            f"reset-password-link route should exist. Found: {route_paths}"


# =====================================================================
# 4. PRIVILEGE ESCALATION — "founder" username must not grant role
# =====================================================================
class TestPrivilegeEscalation:
    """Registering with username 'founder' or 'admin' must NOT grant elevated roles."""

    def test_founder_username_does_not_grant_founder_role(self):
        """The registration code should always use 'student' as initial_role."""
        import inspect
        from routes.auth import register
        source = inspect.getsource(register)
        # The old code granted founder/admin role by username
        assert 'initial_role = "founder" if username == "founder"' not in source, \
            "Privilege escalation via username must be removed"

    def test_initial_role_is_always_student(self):
        """Registration must always set initial_role to 'student'."""
        import inspect
        from routes.auth import register
        source = inspect.getsource(register)
        assert 'initial_role = "student"' in source, \
            "initial_role should always be 'student' on registration"


# =====================================================================
# 5. PASSWORD CHANGE — session revocation
# =====================================================================
class TestPasswordChangeSessionRevocation:
    """change-password endpoint must issue a new session token, revoking old one."""

    def test_change_password_issues_new_session(self):
        """After password change, response should include a new token."""
        import inspect
        from routes.auth import change_password
        source = inspect.getsource(change_password)
        assert 'new_session' in source or 'session_token' in source.split('new_password')[1], \
            "change_password should issue a new session token"
        # Verify return includes "token" key
        assert '"token"' in source or "'token'" in source, \
            "change_password response should include new session token"


# =====================================================================
# 6. SCHEMAS — conversation_id, request_id, viz_request_id
# =====================================================================
class TestSchemaExtensions:
    """CompanionChatRequest must have conversation_id, request_id. VisualizationSpec must have viz_request_id."""

    def test_companion_chat_request_has_conversation_id(self):
        from ai.companion.schemas import CompanionChatRequest
        fields = CompanionChatRequest.model_fields
        assert 'conversation_id' in fields, "CompanionChatRequest must have conversation_id field"

    def test_companion_chat_request_has_request_id(self):
        from ai.companion.schemas import CompanionChatRequest
        fields = CompanionChatRequest.model_fields
        assert 'request_id' in fields, "CompanionChatRequest must have request_id field"

    def test_companion_response_has_conversation_id(self):
        from ai.companion.schemas import CompanionResponse
        fields = CompanionResponse.model_fields
        assert 'conversation_id' in fields, "CompanionResponse must have conversation_id field"

    def test_visualization_spec_has_viz_request_id(self):
        from ai.companion.schemas import VisualizationSpec
        fields = VisualizationSpec.model_fields
        assert 'viz_request_id' in fields, "VisualizationSpec must have viz_request_id field"

    def test_conversation_id_is_optional(self):
        from ai.companion.schemas import CompanionChatRequest
        # Should be optional — can create without providing it
        req = CompanionChatRequest(message="test")
        assert req.conversation_id is None

    def test_request_id_is_optional(self):
        from ai.companion.schemas import CompanionChatRequest
        req = CompanionChatRequest(message="test")
        assert req.request_id is None

    def test_viz_request_id_optional_in_spec(self):
        from ai.companion.schemas import VisualizationSpec
        spec = VisualizationSpec(viz_type="deque", title="Test", initial_state=[1, 2])
        assert spec.viz_request_id is None


# =====================================================================
# 7. DEQUE IN viz_simulator — verify structure dispatch
# =====================================================================
class TestDequeDispatch:
    """DeterministicSimulator.simulate() must route deque correctly."""

    def test_simulate_deque_dispatches_correctly(self):
        from ai.companion.viz_simulator import DeterministicSimulator, VisualizationPlan
        plan = VisualizationPlan(structure="deque", operation="push_pop_both_ends",
                                 initial_values=[1, 2, 3], target_value=10)
        result = DeterministicSimulator.simulate(plan)
        assert result is not None, "simulate() should handle 'deque' structure"
        assert result.viz_type == "deque"

    def test_simulate_queue_still_works(self):
        from ai.companion.viz_simulator import DeterministicSimulator, VisualizationPlan
        plan = VisualizationPlan(structure="queue", operation="enqueue_dequeue",
                                 initial_values=[5, 10], target_value=15)
        result = DeterministicSimulator.simulate(plan)
        assert result is not None, "simulate() should still handle 'queue'"
        assert result.viz_type in ("queue", "circular_queue")

    def test_simulate_deque_not_returning_queue_viz_type(self):
        """Deque must NOT return viz_type='queue'."""
        from ai.companion.viz_simulator import DeterministicSimulator, VisualizationPlan
        plan = VisualizationPlan(structure="deque", operation="pushFront",
                                 initial_values=[1], target_value=99)
        result = DeterministicSimulator.simulate(plan)
        assert result is not None
        assert result.viz_type != "queue", "Deque should not return viz_type='queue'"


# =====================================================================
# 8. EMAIL DISPATCH — dev fallback behavior
# =====================================================================
class TestEmailDispatch:
    """Email dispatch helpers must log server-side, never raise, never return tokens."""

    def test_dispatch_verification_email_does_not_raise(self):
        from routes.auth import _dispatch_verification_email
        # Should not raise even without SMTP config
        try:
            _dispatch_verification_email("test@example.com", "TestUser", "vfy_abc123")
        except Exception as e:
            pytest.fail(f"_dispatch_verification_email raised unexpectedly: {e}")

    def test_dispatch_password_reset_email_does_not_raise(self):
        from routes.auth import _dispatch_password_reset_email
        try:
            _dispatch_password_reset_email("test@example.com", "TestUser", "rst_abc123")
        except Exception as e:
            pytest.fail(f"_dispatch_password_reset_email raised unexpectedly: {e}")

    def test_get_email_config_reads_env_vars(self):
        from routes.auth import _get_email_config
        os.environ['SMTP_HOST'] = 'smtp.test.com'
        os.environ['SMTP_USER'] = 'user@test.com'
        try:
            cfg = _get_email_config()
            assert cfg['host'] == 'smtp.test.com'
            assert cfg['user'] == 'user@test.com'
        finally:
            os.environ.pop('SMTP_HOST', None)
            os.environ.pop('SMTP_USER', None)

    def test_email_config_default_port_is_587(self):
        from routes.auth import _get_email_config
        os.environ.pop('SMTP_PORT', None)
        cfg = _get_email_config()
        assert cfg['port'] == 587


# =====================================================================
# 9. DETERMINISTIC PROBLEM/CODE ALIGNMENT (Requirement 5)
# =====================================================================
class TestProblemCodeMismatch:
    """Detects when student code solves a DIFFERENT problem than active problem."""

    def test_detects_palindrome_code_in_two_sum_problem(self):
        from ai.companion.context_manager import ContextManager
        alert = ContextManager.detect_problem_code_mismatch(
            problem_title="Two Sum",
            problem_description="Given an array of integers nums and an integer target...",
            current_code="def isPalindrome(s: str) -> bool:\n    return s == s[::-1]"
        )
        assert alert is not None
        assert "palindrome" in alert.lower()
        assert "Two Sum" in alert

    def test_detects_twosum_code_in_reverse_linked_list(self):
        from ai.companion.context_manager import ContextManager
        alert = ContextManager.detect_problem_code_mismatch(
            problem_title="Reverse Linked List",
            problem_description="Given the head of a singly linked list, reverse the list...",
            current_code="def twoSum(nums, target):\n    seen = {}\n    for i, n in enumerate(nums): pass"
        )
        assert alert is not None
        assert "two sum" in alert.lower()
        assert "Reverse Linked List" in alert

    def test_no_false_positive_when_code_matches_problem(self):
        from ai.companion.context_manager import ContextManager
        alert = ContextManager.detect_problem_code_mismatch(
            problem_title="Valid Palindrome",
            problem_description="A phrase is a palindrome if...",
            current_code="def isPalindrome(s: str) -> bool:\n    return s == s[::-1]"
        )
        assert alert is None, "Should not alert when code matches problem topic"

    def test_handles_empty_or_none(self):
        from ai.companion.context_manager import ContextManager
        assert ContextManager.detect_problem_code_mismatch(None, None, None) is None
        assert ContextManager.detect_problem_code_mismatch("Two Sum", "", None) is None


# =====================================================================
# RUN SUMMARY
# =====================================================================
if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])

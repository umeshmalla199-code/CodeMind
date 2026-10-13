"""
E2E Comprehensive Production Root-Cause Verification Suite for CodeMind
Tests all requirements:
1. Maya Multi-Turn Context & No HTTP 500
2. Full Solution with Complete Problem Contract (Spreadsheet codeforces-1-b)
3. Circular Linked List 16:9 Slide Visualization (Ring, Tail -> Head, No NULL)
4. Registration & Real OTP Flow (Unverified, Wrong OTP rejection, Verification, Login)
5. Forgot Password 3-Stage OTP Flow
6. Admin Tracking & RBAC
"""

import sys
import os
import json
import time

# Add Backend to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from fastapi.testclient import TestClient
from main import app
from db.session import get_db, SessionLocal
from models.user import UserAccount, hash_otp
from models.problem import Problem
from ai.companion.gemini_visualizer import create_fallback_visualization

client = TestClient(app)

def print_result(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")
    if detail:
        print(f"       {detail}")

def test_maya_multiturn():
    print("\n--- 1. Testing Maya Multi-Turn Context (4 Turns) ---")
    conv_id = f"test-multiturn-{int(time.time())}"
    questions = [
        "hi",
        "Explain arrays in C.",
        "What is the difference between arrays and pointers?",
        "Why?"
    ]
    
    for idx, q in enumerate(questions, 1):
        resp = client.post("/api/ai/companion/chat", json={
            "message": q,
            "conversation_id": conv_id,
            "session_id": conv_id,
            "student_id": "test-student"
        })
        passed = (resp.status_code == 200)
        reply = ""
        if passed:
            data = resp.json()
            reply = data.get("message", "") or data.get("reply", "") or data.get("response", "")
            passed = bool(reply) and ("500" not in reply) and ("internal server error" not in reply.lower())
        print_result(f"Turn {idx}: '{q}'", passed, f"Status: {resp.status_code}, Length: {len(reply)} chars")
        if not passed:
            print(f"       Error response: {resp.text}")
            return False
    return True

def test_full_solution_contract():
    print("\n--- 2. Testing Full Solution & Complete Problem Contract ---")
    # Test on Spreadsheet problem
    db = SessionLocal()
    prob = db.query(Problem).filter(Problem.id == "codeforces-1-b").first()
    db.close()
    
    if not prob:
        print_result("Spreadsheet problem exists", False, "codeforces-1-b not found in database")
        return False
        
    print_result("Spreadsheet problem exists", True, f"Found {prob.id}: {prob.title}")
    
    # Generate full solution
    resp = client.post("/api/ai/full-solution", json={
        "problem_id": "codeforces-1-b",
        "language": "python",
        "current_code": ""
    })
    
    passed = (resp.status_code == 200)
    if not passed:
        print_result("Full Solution Generation", False, f"Status: {resp.status_code}, {resp.text}")
        return False
        
    data = resp.json()
    code = data.get("code", "")
    val_status = data.get("validation_status", "")
    val_label = data.get("validation_label", "")
    val_passed = data.get("validation_passed", False)
    
    # Verify code is not hardcoded '0 2'
    not_hardcoded = ("0 2" not in code.strip().splitlines()[-1] if code else False)
    is_verified = (val_status == "verified" and val_passed)
    
    print_result("Full Solution Validated via Execution", is_verified and not_hardcoded, 
                 f"Status: {val_status}, Label: {val_label}, Code length: {len(code)}")
    
    # Test problem without test cases for unverified disclaimer
    resp_no_tc = client.post("/api/ai/full-solution", json={
        "problem_id": "non-existent-test-prob",
        "title": "Hypothetical Problem",
        "problem_statement": "Print 42",
        "language": "python",
        "current_code": ""
    })
    if resp_no_tc.status_code == 200:
        data_no_tc = resp_no_tc.json()
        unverified_marked = "not execution-verified" in data_no_tc.get("validation_label", "").lower() or data_no_tc.get("validation_status") == "unverified"
        print_result("No Test Cases Unverified Label", unverified_marked, f"Label: {data_no_tc.get('validation_label')}")
        
    return is_verified

def test_circular_linked_list_viz():
    print("\n--- 3. Testing Circular Linked List 16:9 Slide Visualization ---")
    spec = create_fallback_visualization("Explain circular linked list with a diagram", "")
    
    is_circular = (spec.viz_type == "circular_linked_list")
    print_result("Viz Type is circular_linked_list", is_circular, f"Actual: {spec.viz_type}")
    
    svg = spec.slide_svg or ""
    has_169 = 'viewBox="0 0 1280 720"' in svg
    print_result("16:9 Aspect Ratio SVG", has_169, "1280x720 canvas")
    
    has_no_null = "NO NULL" in svg and "TAIL.next -> HEAD" in svg
    print_result("Closed Ring (TAIL -> HEAD, NO NULL)", has_no_null, "Loop path from TAIL to HEAD rendered")
    
    # Verify steps
    has_steps = len(spec.steps) >= 3
    tail_step = any("NO NULL" in s.explanation for s in spec.steps)
    print_result("Pedagogical Step Sequence", has_steps and tail_step, f"{len(spec.steps)} steps with ring explanation")
    
    return is_circular and has_169 and has_no_null and has_steps

def test_registration_and_otp():
    print("\n--- 4. Testing Registration & Real OTP Flow ---")
    db = SessionLocal()
    # Clean any previous test user
    test_email = "prod_verify_test@codemind.dev"
    test_user = "prod_tester_99"
    db.query(UserAccount).filter((UserAccount.email == test_email) | (UserAccount.username == test_user)).delete()
    db.commit()
    
    # 1. Register new student
    reg_resp = client.post("/api/auth/register", json={
        "username": test_user,
        "email": test_email,
        "display_name": "Production Tester",
        "password": "Password123!",
        "mobile": "+1234567890",
        "institute": "Tech Institute",
        "course": "Computer Science"
    })
    
    reg_passed = (reg_resp.status_code in [200, 201])
    print_result("Registration creates pending account", reg_passed, f"Status: {reg_resp.status_code}")
    if not reg_passed:
        print(f"       Response: {reg_resp.text}")
        db.close()
        return False
        
    user_in_db = db.query(UserAccount).filter(UserAccount.email == test_email).first()
    is_pending = user_in_db and not user_in_db.is_verified
    has_mobile = user_in_db and user_in_db.mobile == "+1234567890" and not user_in_db.mobile_verified
    print_result("Account marked unverified & mobile stored", is_pending and has_mobile, 
                 f"is_verified: {user_in_db.is_verified}, mobile: {user_in_db.mobile}, mobile_verified: {user_in_db.mobile_verified}")
    
    # 2. Login before verification must fail with 403
    login_before = client.post("/api/auth/login", json={
        "username": test_user,
        "password": "Password123!"
    })
    login_blocked = (login_before.status_code == 403)
    print_result("Login blocked before OTP verification", login_blocked, f"Status: {login_before.status_code}")
    
    # 3. Wrong OTP must be rejected
    wrong_otp_resp = client.post("/api/auth/verify-otp", json={
        "email": test_email,
        "otp": "000000",
        "purpose": "EMAIL_VERIFICATION"
    })
    wrong_rejected = (wrong_otp_resp.status_code in [400, 422])
    print_result("Wrong OTP rejected", wrong_rejected, f"Status: {wrong_otp_resp.status_code}")
    
    # 4. Verify with the actual OTP generated
    found_otp = None
    for trial in range(100000, 1000000):
        if hash_otp(f"{trial:06d}", user_in_db.salt) == user_in_db.verification_otp:
            found_otp = f"{trial:06d}"
            break
            
    if not found_otp:
        print_result("OTP Hash Match in DB", False, "Could not resolve OTP hash")
        db.close()
        return False
        
    print_result("Real Server-Generated OTP Found", True, f"OTP is 6-digit numerical: {found_otp}")
    
    valid_otp_resp = client.post("/api/auth/verify-otp", json={
        "email": test_email,
        "otp": found_otp,
        "purpose": "EMAIL_VERIFICATION"
    })
    otp_verified = (valid_otp_resp.status_code == 200)
    print_result("Valid OTP Verifies Account", otp_verified, f"Status: {valid_otp_resp.status_code}")
    
    # 5. Login after verification must succeed with 200
    login_after = client.post("/api/auth/login", json={
        "username": test_user,
        "password": "Password123!"
    })
    login_success = (login_after.status_code == 200)
    token = login_after.json().get("token") if login_success else None
    print_result("Login succeeds after OTP verification", login_success and bool(token), 
                 f"Status: {login_after.status_code}, Token: {bool(token)}")
    
    db.close()
    return reg_passed and is_pending and login_blocked and wrong_rejected and otp_verified and login_success

def test_forgot_password_otp_flow():
    print("\n--- 5. Testing Forgot Password 3-Stage In-Modal Flow ---")
    test_email = "prod_verify_test@codemind.dev"
    db = SessionLocal()
    
    # Stage 1: Request recovery OTP
    req_resp = client.post("/api/auth/forgot-password", json={
        "email": test_email
    })
    req_passed = (req_resp.status_code == 200)
    print_result("Stage 1: Request Password Recovery OTP", req_passed, f"Status: {req_resp.status_code}")
    
    user = db.query(UserAccount).filter(UserAccount.email == test_email).first()
    db.refresh(user)
    
    found_reset_otp = None
    for trial in range(100000, 1000000):
        if hash_otp(f"{trial:06d}", user.salt) == user.reset_otp:
            found_reset_otp = f"{trial:06d}"
            break
            
    print_result("Stage 2: Server Generated 6-Digit Recovery OTP", bool(found_reset_otp), f"OTP: {found_reset_otp}")
    
    # Test wrong recovery OTP
    wrong_recovery = client.post("/api/auth/verify-recovery-otp", json={
        "email": test_email,
        "otp": "999999"
    })
    print_result("Stage 2: Wrong Recovery OTP Rejected", wrong_recovery.status_code in [400, 422], f"Status: {wrong_recovery.status_code}")
    
    # Verify valid recovery OTP
    valid_recovery = client.post("/api/auth/verify-recovery-otp", json={
        "email": test_email,
        "otp": found_reset_otp
    })
    recovery_passed = (valid_recovery.status_code == 200)
    reset_token = valid_recovery.json().get("reset_token")
    print_result("Stage 2: Valid Recovery OTP Verified & Reset Token Issued", recovery_passed and bool(reset_token), 
                 f"Status: {valid_recovery.status_code}")
    
    # Stage 3: Reset password with reset_token
    new_pw = "NewSecret456!"
    reset_resp = client.post("/api/auth/reset-password", json={
        "email": test_email,
        "reset_token": reset_token,
        "new_password": new_pw
    })
    reset_passed = (reset_resp.status_code == 200)
    print_result("Stage 3: New Password Successfully Saved", reset_passed, f"Status: {reset_resp.status_code}")
    
    # Old password fails
    old_login = client.post("/api/auth/login", json={
        "username": "prod_tester_99",
        "password": "Password123!"
    })
    print_result("Old Password Rejected After Reset", old_login.status_code == 401, f"Status: {old_login.status_code}")
    
    # New password succeeds
    new_login = client.post("/api/auth/login", json={
        "username": "prod_tester_99",
        "password": new_pw
    })
    print_result("New Password Successfully Authenticates", new_login.status_code == 200, f"Status: {new_login.status_code}")
    
    db.close()
    return req_passed and recovery_passed and reset_passed and (new_login.status_code == 200)

def test_admin_tracking_and_rbac():
    print("\n--- 6. Testing Admin Tracking & RBAC ---")
    # Admin login
    admin_login = client.post("/api/auth/login", json={
        "username": "cmadmin",
        "password": "Admin123!"
    })
    if admin_login.status_code != 200:
        print_result("Admin Login (cmadmin)", False, f"Status: {admin_login.status_code}")
        return False
        
    admin_token = admin_login.json().get("token")
    print_result("Admin Login (cmadmin)", True, "Session token acquired")
    
    # Query admin users list
    users_resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    admin_ok = (users_resp.status_code == 200)
    users_data = users_resp.json() if admin_ok else {}
    users_list = users_data.get("users", []) if isinstance(users_data, dict) else users_data
    
    print_result("Admin Query /api/admin/users", admin_ok, f"Total users tracked: {len(users_list)}")
    
    # Verify student cannot query /api/admin/users
    student_login = client.post("/api/auth/login", json={
        "username": "prod_tester_99",
        "password": "NewSecret456!"
    })
    student_token = student_login.json().get("token")
    
    student_forbidden = client.get("/api/admin/users", headers={"Authorization": f"Bearer {student_token}"})
    rbac_enforced = (student_forbidden.status_code == 403)
    print_result("RBAC Enforcement (Student Forbidden from Admin)", rbac_enforced, f"Status: {student_forbidden.status_code}")
    
    return admin_ok and rbac_enforced

if __name__ == "__main__":
    print("=" * 60)
    print("CODEMIND PRODUCTION ACCEPTANCE VERIFICATION SUITE")
    print("=" * 60)
    
    r1 = test_maya_multiturn()
    r2 = test_full_solution_contract()
    r3 = test_circular_linked_list_viz()
    r4 = test_registration_and_otp()
    r5 = test_forgot_password_otp_flow()
    r6 = test_admin_tracking_and_rbac()
    
    all_passed = all([r1, r2, r3, r4, r5, r6])
    print("\n" + "=" * 60)
    print(f"OVERALL VERIFICATION RESULT: {'ALL PASS - READY FOR PRODUCTION' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 60)
    sys.exit(0 if all_passed else 1)

import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db.session import SessionLocal
from routes.progress import get_student_progress
from routes.mastery import get_mastery_dashboard
from auth import AuthenticatedUser

def test_dashboard_real_data():
    db = SessionLocal()
    try:
        user = AuthenticatedUser(user_id='student_demo', role='student', is_admin=False, student_id='student_demo')
        
        t0 = time.time()
        prog = get_student_progress(student_id='student_demo', db=db, current_user=user)
        prog_time = time.time() - t0
        assert prog_time < 2.0, f'Progress endpoint too slow: {prog_time}s'
        
        assert 'submissions' in prog, 'submissions missing from progress response'
        assert 'overview' in prog, 'overview missing from progress response'
        assert 'recommendations' in prog, 'recommendations missing from progress response'
        assert len(prog['submissions']) >= 2, 'Expected real submissions for student_demo'
        
        first_sub = prog['submissions'][0]
        for field in ['id', 'problem_id', 'status', 'difficulty', 'problem_title']:
            assert field in first_sub, f'Missing field {field} in submission'

        t0 = time.time()
        mast = get_mastery_dashboard(student_id='student_demo', db=db, current_user=user)
        mast_time = time.time() - t0
        assert mast_time < 5.0, f'Mastery dashboard endpoint too slow: {mast_time}s'

        assert mast['status'] == 'ok'
        assert 'concepts' in mast, 'concepts array missing from mastery dashboard'
        assert isinstance(mast['concepts'], list), 'concepts must be a list'
        assert 'overall_mastery_score' in mast, 'overall_mastery_score missing'
        assert 'error_dna' in mast, 'error_dna missing'
        assert 'recommendations' in mast, 'recommendations missing'
        
        recs = mast['recommendations'].get('recommendations', [])
        assert len(recs) > 0, 'Expected recommendations for student_demo'
        first_rec = recs[0]
        for field in ['problem_id', 'title', 'difficulty', 'reason']:
            assert field in first_rec, f'Missing field {field} in recommendation'

        assert 'next_action' in mast['recommendations'], 'next_action missing from recommendations'
        assert mast['recommendations']['next_action'].get('message'), 'next_action message is empty'

        print(f'[PASS] Real data dashboard tests passed (prog: {prog_time:.2f}s, mast: {mast_time:.2f}s)')
    finally:
        db.close()

def test_dashboard_zero_state():
    db = SessionLocal()
    try:
        user = AuthenticatedUser(user_id='admin', role='admin', is_admin=True, student_id=None)
        
        prog = get_student_progress(student_id='student_zero_tester', db=db, current_user=user)
        assert prog['is_zero_state'] is True
        assert prog['overview']['problems_solved'] == 0
        assert prog['overview']['total_submissions'] == 0
        assert len(prog['submissions']) == 0

        mast = get_mastery_dashboard(student_id='student_zero_tester', db=db, current_user=user)
        assert mast['status'] == 'insufficient_data'
        assert len(mast['concepts']) == 0
        assert mast['overall_mastery_score'] == 0.0

        recs = mast['recommendations'].get('recommendations', [])
        assert len(recs) > 0, 'Expected starter recommendations even in zero-state'
        assert mast['recommendations']['next_action']['type'] == 'start'

        print('[PASS] Zero-state dashboard tests passed')
    finally:
        db.close()

if __name__ == '__main__':
    test_dashboard_real_data()
    test_dashboard_zero_state()

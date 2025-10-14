# test_storage_modules.py
"""Test storage modules locally"""
import sys

sys.path.append('lambdas/shared')

from storage_s3 import S3DesignHistoryStorage, S3ResultsStorage


def test_storage():
    print("Testing S3 storage modules...")

    # Test session
    test_session = "opt-test-20251013-local"

    # Test design history
    print("\n1. Testing Design History Storage")
    design_storage = S3DesignHistoryStorage(session_id=test_session)

    test_design = {
        'geometry_id': 'NACA4412_a2.0',
        'thickness': 0.12,
        'max_camber': 0.04,
        'camber_position': 0.40,
        'alpha': 2.0,
        'Cl': 0.48,
        'Cd': 0.0142,
        'L_D': 33.8,
        'converged': True,
        'reynolds': 500000,
        'iterations': 230,
        'computation_time': 65.3
    }

    design_storage.write_design(test_design)
    designs = design_storage.read_design_history()
    print(f"✓ Wrote and read {len(designs)} design(s)")

    # Test results
    print("\n2. Testing Results Storage")
    results_storage = S3ResultsStorage(session_id=test_session)

    test_result = {
        'iteration': 1,
        'candidate_count': 1,
        'best_cd': 0.0142,
        'best_geometry_id': 'NACA4412_a2.0',
        'strategy': 'baseline',
        'trust_radius': 0.0,
        'confidence': 1.0,
        'notes': 'Test iteration'
    }

    results_storage.write_result(test_result)
    results = results_storage.read_results()
    print(f"✓ Wrote and read {len(results)} result(s)")

    print("\n✅ All storage tests passed!")
    print(f"\nVerify in S3:")
    print(f"  sessions/{test_session}/design_history.csv")
    print(f"  sessions/{test_session}/results.csv")


if __name__ == "__main__":
    test_storage()




















































































































































































































































































































    
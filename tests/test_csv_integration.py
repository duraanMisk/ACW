"""
Test CSV storage integration for CFD optimization.

This script:
1. Clears existing CSV files
2. Simulates a full optimization loop
3. Verifies data is correctly persisted
4. Checks data can be read back correctly
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'lambdas', 'shared'))

from storage import (
    DesignHistoryStorage,
    ResultsStorage,
    clear_all_data,
    get_optimization_summary
)
import json
from datetime import datetime


def test_design_history_storage():
    """Test design history storage functionality."""
    print("\n" + "=" * 60)
    print("TEST 1: Design History Storage")
    print("=" * 60)

    storage = DesignHistoryStorage()

    # Test write
    print("\n1.1 Testing write operations...")
    test_designs = [
        {
            'geometry_id': 'NACA4412_a2.0',
            'thickness': 0.12,
            'max_camber': 0.04,
            'camber_position': 0.40,
            'alpha': 2.0,
            'Cl': 0.35,
            'Cd': 0.0142,
            'L_D': 24.6,
            'converged': True,
            'reynolds': 500000,
            'iterations': 230,
            'computation_time': 65.3
        },
        {
            'geometry_id': 'NACA4410_a2.5',
            'thickness': 0.10,
            'max_camber': 0.04,
            'camber_position': 0.40,
            'alpha': 2.5,
            'Cl': 0.42,
            'Cd': 0.0138,
            'L_D': 30.4,
            'converged': True,
            'reynolds': 500000,
            'iterations': 215,
            'computation_time': 58.7
        },
        {
            'geometry_id': 'NACA4408_a3.0',
            'thickness': 0.08,
            'max_camber': 0.04,
            'camber_position': 0.40,
            'alpha': 3.0,
            'Cl': 0.48,
            'Cd': 0.0135,
            'L_D': 35.6,
            'converged': True,
            'reynolds': 500000,
            'iterations': 198,
            'computation_time': 52.1
        }
    ]

    for design in test_designs:
        storage.write_design(design)

    print(f"✓ Wrote {len(test_designs)} designs to history")

    # Test read
    print("\n1.2 Testing read operations...")
    history_df = storage.read_design_history()

    if len(history_df) != len(test_designs):
        print(f"✗ FAIL: Expected {len(test_designs)} designs, got {len(history_df)}")
        return False

    print(f"✓ Read {len(history_df)} designs from history")

    # Test get_best_design
    print("\n1.3 Testing get_best_design...")
    best = storage.get_best_design(constraint_cl_min=0.30)

    if best is None:
        print("✗ FAIL: Could not find best design")
        return False

    expected_best_id = 'NACA4408_a3.0'  # Lowest Cd that satisfies constraint
    if best['geometry_id'] != expected_best_id:
        print(f"✗ FAIL: Expected best design {expected_best_id}, got {best['geometry_id']}")
        return False

    print(f"✓ Correctly identified best design: {best['geometry_id']} (Cd={best['Cd']})")

    # Test get_latest_designs
    print("\n1.4 Testing get_latest_designs...")
    latest = storage.get_latest_designs(n=2)

    if len(latest) != 2:
        print(f"✗ FAIL: Expected 2 latest designs, got {len(latest)}")
        return False

    print(f"✓ Retrieved {len(latest)} latest designs")

    print("\n✓ ALL DESIGN HISTORY TESTS PASSED")
    return True


def test_results_storage():
    """Test results storage functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: Results Storage")
    print("=" * 60)

    storage = ResultsStorage()

    # Test write
    print("\n2.1 Testing write operations...")
    test_results = [
        {
            'iteration': 1,
            'candidate_count': 1,
            'best_cd': 0.0142,
            'best_geometry_id': 'NACA4412_a2.0',
            'strategy': 'baseline',
            'trust_radius': 0.0,
            'confidence': 1.0,
            'notes': 'Initial baseline'
        },
        {
            'iteration': 2,
            'candidate_count': 5,
            'best_cd': 0.0138,
            'best_geometry_id': 'NACA4410_a2.5',
            'strategy': 'explore',
            'trust_radius': 0.015,
            'confidence': 0.65,
            'notes': 'Exploration phase'
        },
        {
            'iteration': 3,
            'candidate_count': 4,
            'best_cd': 0.0135,
            'best_geometry_id': 'NACA4408_a3.0',
            'strategy': 'exploit',
            'trust_radius': 0.010,
            'confidence': 0.75,
            'notes': 'Exploitation phase'
        }
    ]

    for result in test_results:
        storage.write_result(result)

    print(f"✓ Wrote {len(test_results)} iteration results")

    # Test read
    print("\n2.2 Testing read operations...")
    results_df = storage.read_results()

    if len(results_df) != len(test_results):
        print(f"✗ FAIL: Expected {len(test_results)} results, got {len(results_df)}")
        return False

    print(f"✓ Read {len(results_df)} iteration results")

    # Test get_latest_iteration
    print("\n2.3 Testing get_latest_iteration...")
    latest = storage.get_latest_iteration()

    if latest is None:
        print("✗ FAIL: Could not get latest iteration")
        return False

    if latest['iteration'] != 3:
        print(f"✗ FAIL: Expected iteration 3, got {latest['iteration']}")
        return False

    print(f"✓ Latest iteration: {latest['iteration']}")

    # Test calculate_improvement
    print("\n2.4 Testing calculate_improvement...")
    improvement = storage.calculate_improvement()

    if improvement is None:
        print("✗ FAIL: Could not calculate improvement")
        return False

    # Expected: (0.0138 - 0.0135) / 0.0138 * 100 ≈ 2.17%
    expected_improvement = 2.17
    if abs(improvement - expected_improvement) > 0.5:
        print(f"✗ FAIL: Expected ~{expected_improvement}%, got {improvement}%")
        return False

    print(f"✓ Improvement: {improvement}%")

    print("\n✓ ALL RESULTS STORAGE TESTS PASSED")
    return True


def test_optimization_summary():
    """Test get_optimization_summary function."""
    print("\n" + "=" * 60)
    print("TEST 3: Optimization Summary")
    print("=" * 60)

    summary = get_optimization_summary()

    print("\nSummary:")
    print(f"  Total designs evaluated: {summary['total_designs_evaluated']}")
    print(f"  Total iterations: {summary['total_iterations']}")
    print(f"  Best design: {summary['best_design']['geometry_id'] if summary['best_design'] else 'None'}")
    print(f"  Latest iteration: {summary['latest_iteration']['iteration'] if summary['latest_iteration'] else 'None'}")
    print(f"  Recent improvement: {summary['improvement_pct']}%")

    # Validate summary
    if summary['total_designs_evaluated'] != 3:
        print(f"\n✗ FAIL: Expected 3 designs, got {summary['total_designs_evaluated']}")
        return False

    if summary['total_iterations'] != 3:
        print(f"✗ FAIL: Expected 3 iterations, got {summary['total_iterations']}")
        return False

    if summary['best_design']['geometry_id'] != 'NACA4408_a3.0':
        print(f"✗ FAIL: Wrong best design")
        return False

    print("\n✓ OPTIMIZATION SUMMARY TEST PASSED")
    return True


def test_csv_file_structure():
    """Verify CSV files have correct structure."""
    print("\n" + "=" * 60)
    print("TEST 4: CSV File Structure")
    print("=" * 60)

    import pandas as pd

    # Check design_history.csv
    print("\n4.1 Checking design_history.csv...")
    design_path = '../data/design_history.csv'

    if not os.path.exists(design_path):
        print(f"✗ FAIL: {design_path} does not exist")
        return False

    df = pd.read_csv(design_path)

    expected_columns = [
        'timestamp', 'geometry_id', 'thickness', 'max_camber',
        'camber_position', 'alpha', 'Cl', 'Cd', 'L_D',
        'converged', 'reynolds', 'iterations', 'computation_time'
    ]

    missing_cols = set(expected_columns) - set(df.columns)
    if missing_cols:
        print(f"✗ FAIL: Missing columns: {missing_cols}")
        return False

    print(f"✓ design_history.csv has all {len(expected_columns)} columns")
    print(f"  Rows: {len(df)}")

    # Check results.csv
    print("\n4.2 Checking results.csv...")
    results_path = '../data/results.csv'

    if not os.path.exists(results_path):
        print(f"✗ FAIL: {results_path} does not exist")
        return False

    df = pd.read_csv(results_path)

    expected_columns = [
        'timestamp', 'iteration', 'candidate_count', 'best_cd',
        'best_geometry_id', 'strategy', 'trust_radius', 'confidence', 'notes'
    ]

    missing_cols = set(expected_columns) - set(df.columns)
    if missing_cols:
        print(f"✗ FAIL: Missing columns: {missing_cols}")
        return False

    print(f"✓ results.csv has all {len(expected_columns)} columns")
    print(f"  Rows: {len(df)}")

    print("\n✓ CSV FILE STRUCTURE TEST PASSED")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("CFD OPTIMIZATION CSV STORAGE INTEGRATION TESTS")
    print("=" * 60)

    # Clear existing data
    print("\nClearing existing CSV files...")
    clear_all_data()
    print("✓ Cleared all data\n")

    # Run tests
    tests = [
        ("Design History Storage", test_design_history_storage),
        ("Results Storage", test_results_storage),
        ("Optimization Summary", test_optimization_summary),
        ("CSV File Structure", test_csv_file_structure),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n✗ TEST FAILED WITH EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Final summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! CSV storage integration is working correctly.")
        print("\nNext steps:")
        print("1. Deploy updated Lambda functions (deploy_updated_lambdas.py)")
        print("2. Test with Bedrock Agent in AWS Console")
        return 0
    else:
        print(f"\n⚠ {failed} test(s) failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
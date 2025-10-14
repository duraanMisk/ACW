#!/usr/bin/env python3
"""
Test S3 storage integration for CFD optimization.

Validates:
1. S3 bucket is accessible
2. Session creation works
3. Design storage works
4. Lambda functions can write to S3
"""

import sys
import os

sys.path.append('lambdas/shared')

import boto3
import json
from datetime import datetime
import uuid

from storage_s3 import S3DesignHistoryStorage, S3ResultsStorage
from session_manager import SessionManager

lambda_client = boto3.client('lambda', region_name='us-east-1')


def test_session_manager():
    """Test session creation and management."""
    print("\n" + "=" * 60)
    print("TEST 1: Session Manager")
    print("=" * 60)

    # Create test session
    session_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}"
    manager = SessionManager(session_id)

    print(f"Creating session: {session_id}")

    config = {
        'objective': 'minimize_cd',
        'cl_min': 0.30,
        'reynolds': 500000,
        'max_iter': 3
    }

    session_data = manager.create_session(config)
    print(f"✓ Session created")

    # Retrieve session
    retrieved = manager.get_session()
    assert retrieved is not None, "Could not retrieve session"
    assert retrieved['session_id'] == session_id
    print(f"✓ Session retrieved")

    # Update session
    manager.update_session({
        'current_iteration': 1,
        'best_cd': 0.0142
    })
    print(f"✓ Session updated")

    # Check progress
    progress = manager.get_progress()
    assert progress['current_iteration'] == 1
    print(f"✓ Progress tracking works")
    print(f"  Current iteration: {progress['current_iteration']}/{progress['max_iterations']}")

    return session_id


def test_design_storage(session_id):
    """Test design history storage."""
    print("\n" + "=" * 60)
    print("TEST 2: Design History Storage")
    print("=" * 60)

    storage = S3DesignHistoryStorage(session_id)

    # Write test designs
    test_designs = [
        {
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
        },
        {
            'geometry_id': 'NACA4410_a2.5',
            'thickness': 0.10,
            'max_camber': 0.04,
            'camber_position': 0.40,
            'alpha': 2.5,
            'Cl': 0.52,
            'Cd': 0.0138,
            'L_D': 37.7,
            'converged': True,
            'reynolds': 500000,
            'iterations': 215,
            'computation_time': 58.7
        }
    ]

    for design in test_designs:
        storage.write_design(design)

    print(f"✓ Wrote {len(test_designs)} designs to S3")

    # Read back
    designs = storage.read_all_designs()
    assert len(designs) == len(test_designs), f"Expected {len(test_designs)} designs, got {len(designs)}"
    print(f"✓ Read {len(designs)} designs from S3")

    # Get best design
    best = storage.get_best_design(constraint_cl_min=0.30)
    assert best is not None, "Could not find best design"
    assert best['geometry_id'] == 'NACA4410_a2.5', "Wrong best design"
    print(f"✓ Best design: {best['geometry_id']} (Cd={best['Cd']:.5f})")

    # Get latest designs
    latest = storage.get_latest_designs(n=1)
    assert len(latest) == 1
    print(f"✓ Latest design retrieval works")


def test_results_storage(session_id):
    """Test iteration results storage."""
    print("\n" + "=" * 60)
    print("TEST 3: Results Storage")
    print("=" * 60)

    storage = S3ResultsStorage(session_id)

    # Write test results
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
            'candidate_count': 4,
            'best_cd': 0.0138,
            'best_geometry_id': 'NACA4410_a2.5',
            'strategy': 'explore',
            'trust_radius': 0.015,
            'confidence': 0.65,
            'notes': 'Exploration phase'
        }
    ]

    for result in test_results:
        storage.write_result(result)

    print(f"✓ Wrote {len(test_results)} iteration results to S3")

    # Read back
    results = storage.read_all_results()
    assert len(results) == len(test_results)
    print(f"✓ Read {len(results)} results from S3")

    # Get latest iteration
    latest = storage.get_latest_iteration()
    assert latest['iteration'] == 2
    print(f"✓ Latest iteration: {latest['iteration']}")

    # Calculate improvement
    improvement = storage.calculate_improvement()
    assert improvement is not None
    print(f"✓ Improvement: {improvement:.2f}%")


def test_lambda_integration(session_id):
    """Test Lambda function S3 integration."""
    print("\n" + "=" * 60)
    print("TEST 4: Lambda S3 Integration")
    print("=" * 60)

    # Format Bedrock Agent event
    def format_bedrock_payload(params):
        properties = [
            {'name': k, 'type': 'number' if isinstance(v, (int, float)) else 'string', 'value': str(v)}
            for k, v in params.items()
        ]
        return {
            'requestBody': {
                'content': {
                    'application/json': {
                        'properties': properties
                    }
                }
            }
        }

    # Test generate_geometry
    print("\nTesting generate_geometry...")
    geo_payload = format_bedrock_payload({
        'thickness': 0.12,
        'max_camber': 0.04,
        'camber_position': 0.40,
        'alpha': 2.0,
        'session_id': session_id
    })

    try:
        response = lambda_client.invoke(
            FunctionName='cfd-generate-geometry',
            Payload=json.dumps(geo_payload)
        )
        result = json.loads(response['Payload'].read())
        print(f"✓ generate_geometry responded")
    except Exception as e:
        print(f"✗ generate_geometry failed: {e}")
        return False

    # Test run_cfd
    print("\nTesting run_cfd...")
    cfd_payload = format_bedrock_payload({
        'geometry_id': 'NACA4412_a2.0',
        'reynolds': 500000,
        'session_id': session_id
    })

    try:
        response = lambda_client.invoke(
            FunctionName='cfd-run-cfd',
            Payload=json.dumps(cfd_payload)
        )
        result = json.loads(response['Payload'].read())

        # Extract CFD results
        if 'response' in result and 'responseBody' in result['response']:
            body_str = result['response']['responseBody']['application/json']['body']
            cfd_results = json.loads(body_str)
            print(f"✓ run_cfd responded: Cd={cfd_results.get('Cd')}, Cl={cfd_results.get('Cl')}")
        else:
            print(f"✓ run_cfd responded (raw format)")
    except Exception as e:
        print(f"✗ run_cfd failed: {e}")
        return False

    # Verify data was written to S3
    print("\nVerifying S3 persistence...")
    storage = S3DesignHistoryStorage(session_id)
    designs = storage.read_all_designs()

    # Should have at least one design from our Lambda test
    # Plus the 2 from earlier tests = at least 3 total
    if len(designs) >= 3:
        print(f"✓ Lambda functions writing to S3 correctly ({len(designs)} designs found)")
        return True
    else:
        print(f"⚠ Expected at least 3 designs, found {len(designs)}")
        return False


def main():
    """Run all S3 integration tests."""
    print("=" * 60)
    print("CFD Optimization - S3 Integration Tests")
    print("=" * 60)

    try:
        # Test 1: Session Manager
        session_id = test_session_manager()

        # Test 2: Design Storage
        test_design_storage(session_id)

        # Test 3: Results Storage
        test_results_storage(session_id)

        # Test 4: Lambda Integration
        lambda_success = test_lambda_integration(session_id)

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Test session: {session_id}")
        print(f"\n✓ Session Manager: PASSED")
        print(f"✓ Design Storage: PASSED")
        print(f"✓ Results Storage: PASSED")

        if lambda_success:
            print(f"✓ Lambda Integration: PASSED")
            print("\n🎉 All tests passed! S3 integration is working.")
            print(f"\nTest data stored in S3 under session: {session_id}")
            print("\nNext steps:")
            print("  1. Update all Lambda handlers to use S3 storage")
            print("  2. Update Step Functions to pass session_id")
            print("  3. Test full optimization workflow")
        else:
            print(f"⚠ Lambda Integration: FAILED")
            print("\nCheck Lambda function logs for errors")

        return 0 if lambda_success else 1

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
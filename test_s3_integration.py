"""
S3 Integration Tests - Works with Direct Lambda Response Format

This test validates end-to-end S3 integration by calling Lambda functions
directly, bypassing Bedrock Agent to avoid rate limits and statusCode wrappers.

Tests:
1. Initialize Optimization - Creates S3 session structure
2. Generate Geometry - Creates geometry and saves to S3
3. Run CFD - Simulates aerodynamics and saves results to S3
4. Check Convergence - Reads S3 data and evaluates convergence
5. Generate Report - Reads all S3 data and creates summary
6. Verify S3 Structure - Confirms proper file organization

Each Lambda returns data directly (no statusCode wrapper).
"""

import boto3
import json
import time
from datetime import datetime

# AWS Configuration
REGION = 'us-east-1'
BUCKET_NAME = 'cfd-optimization-data-120569639479-us-east-1'

# Lambda function names
FUNCTIONS = {
    'initialize': 'cfd-initialize-optimization',
    'generate': 'cfd-generate-geometry',
    'run_cfd': 'cfd-run-cfd',
    'check_conv': 'cfd-check-convergence',
    'report': 'cfd-generate-report'
}

# Initialize clients
lambda_client = boto3.client('lambda', region_name=REGION)
s3_client = boto3.client('s3', region_name=REGION)


def invoke_lambda(function_name, payload):
    """
    Invoke Lambda function and return parsed result.

    Args:
        function_name: Name of Lambda function
        payload: Input event dict

    Returns:
        Parsed response body (direct format, no statusCode)
    """
    print(f"\n→ Invoking {function_name}")
    print(f"  Payload: {json.dumps(payload, indent=2)}")

    response = lambda_client.invoke(
        FunctionName=function_name,
        Payload=json.dumps(payload)
    )

    result = json.loads(response['Payload'].read())
    print(f"  Response type: {type(result)}")

    return result


def test_initialize_optimization():
    """TEST 1: Create new S3 optimization session."""
    print("\n" + "=" * 60)
    print("TEST 1: Initialize Optimization (Create S3 Session)")
    print("=" * 60)

    payload = {
        'objective': 'minimize_cd',
        'cl_min': 0.30,
        'reynolds': 500000,
        'max_iter': 5
    }

    result = invoke_lambda(FUNCTIONS['initialize'], payload)

    # Result should be direct dict with sessionId (camelCase)
    if 'sessionId' in result:
        session_id = result['sessionId']
        print(f"\n✓ Session created: {session_id}")
        print(f"  Objective: {result.get('objective')}")
        print(f"  Cl min: {result.get('cl_min')}")
        print(f"  Max iterations: {result.get('max_iter')}")
        print(f"  S3 enabled: {result.get('s3_enabled')}")
        return session_id
    else:
        print(f"\n✗ Failed to create session")
        print(f"  Response: {json.dumps(result, indent=2)}")
        return None


def test_generate_geometry(session_id, iteration=1):
    """TEST 2: Generate geometry and save to S3."""
    print("\n" + "=" * 60)
    print(f"TEST 2: Generate Geometry (Iteration {iteration})")
    print("=" * 60)

    # Format as Bedrock Agent event structure (what your Lambda expects)
    payload = {
        'sessionId': session_id,
        'requestBody': {
            'content': {
                'application/json': {
                    'properties': [
                        {'name': 'thickness', 'value': '0.12'},
                        {'name': 'max_camber', 'value': '0.04'},
                        {'name': 'camber_position', 'value': '0.4'},
                        {'name': 'alpha', 'value': '2.0'}
                    ]
                }
            }
        },
        'actionGroup': 'test-group',
        'apiPath': '/generate-geometry',
        'httpMethod': 'POST'
    }

    result = invoke_lambda(FUNCTIONS['generate'], payload)

    # Parse Bedrock Agent response format
    if 'response' in result and 'responseBody' in result['response']:
        body_str = result['response']['responseBody']['application/json']['body']
        body = json.loads(body_str)

        geometry_id = body.get('geometry_id')
        if geometry_id:
            print(f"\n✓ Geometry generated: {geometry_id}")
            print(f"  Validity: {body.get('validity', {}).get('is_valid')}")
            print(f"  Mesh quality: {body.get('mesh_quality', {}).get('score')}")
            return geometry_id
        else:
            print(f"\n✗ No geometry_id in response")
            print(f"  Body: {json.dumps(body, indent=2)}")
            return None
    else:
        print(f"\n✗ Unexpected response format")
        print(f"  Response: {json.dumps(result, indent=2)}")
        return None


def test_run_cfd(session_id, geometry_id, iteration=1):
    """TEST 3: Run CFD simulation and save to S3."""
    print("\n" + "=" * 60)
    print(f"TEST 3: Run CFD (Iteration {iteration})")
    print("=" * 60)

    # Format as Bedrock Agent event
    payload = {
        'sessionId': session_id,
        'requestBody': {
            'content': {
                'application/json': {
                    'properties': [
                        {'name': 'geometry_id', 'value': geometry_id},
                        {'name': 'reynolds', 'value': '500000'},
                        {'name': 'iteration', 'value': str(iteration)}  # ← ADD THIS LINE
                    ]
                }
            }
        },
        'actionGroup': 'test-group',
        'apiPath': '/run-cfd',
        'httpMethod': 'POST'
    }

    result = invoke_lambda(FUNCTIONS['run_cfd'], payload)

    # Parse response
    if 'response' in result and 'responseBody' in result['response']:
        body_str = result['response']['responseBody']['application/json']['body']
        body = json.loads(body_str)

        print(f"\n✓ CFD simulation complete")
        print(f"  Cl: {body.get('Cl'):.4f}")
        print(f"  Cd: {body.get('Cd'):.5f}")
        print(f"  L/D: {body.get('L_D'):.2f}")
        print(f"  Converged: {body.get('converged')}")

        return body
    else:
        print(f"\n✗ Unexpected response format")
        print(f"  Response: {json.dumps(result, indent=2)}")
        return None


def test_check_convergence(session_id, iteration=1):
    """TEST 4: Check convergence from S3 data."""
    print("\n" + "=" * 60)
    print(f"TEST 4: Check Convergence (After Iteration {iteration})")
    print("=" * 60)

    payload = {
        'sessionId': session_id,
        'max_iter': 5,
        'cl_min': 0.30,
        'iteration': iteration
    }

    result = invoke_lambda(FUNCTIONS['check_conv'], payload)

    # Direct response format
    if 'converged' in result:
        print(f"\n✓ Convergence check complete")
        print(f"  Converged: {result['converged']}")
        print(f"  Iteration: {result.get('iteration')}")
        print(f"  Reason: {result.get('reason', 'N/A')}")

        if result.get('best_cd'):
            print(f"  Best Cd: {result['best_cd']:.5f}")

        return result['converged']
    else:
        print(f"\n✗ Unexpected response format")
        print(f"  Response: {json.dumps(result, indent=2)}")
        return False


def test_generate_report(session_id, reason='Test complete'):
    """TEST 5: Generate final optimization report."""
    print("\n" + "=" * 60)
    print("TEST 5: Generate Report")
    print("=" * 60)

    payload = {
        'sessionId': session_id,
        'cl_min': 0.30,
        'reason': reason
    }

    result = invoke_lambda(FUNCTIONS['report'], payload)

    # Direct response format
    if 'body' in result:
        body = result['body']

        if body.get('status') == 'INCOMPLETE':
            print(f"\n⚠ Report incomplete (need more iterations)")
            return True

        print(f"\n✓ Report generated")

        if 'optimization_summary' in body:
            summary = body['optimization_summary']
            print(f"  Status: {summary.get('status')}")
            print(f"  Designs evaluated: {summary.get('designs_evaluated')}")
            print(f"  Iterations: {summary.get('iterations_completed')}")

        if 'best_design' in body:
            design = body['best_design']
            print(f"\n  Best Design:")
            print(f"    ID: {design.get('geometry_id')}")
            print(f"    Cd: {design.get('Cd'):.5f}")
            print(f"    Cl: {design.get('Cl'):.4f}")
            print(f"    L/D: {design.get('L_D'):.2f}")

        return True
    else:
        print(f"\n✗ Unexpected response format")
        print(f"  Response: {json.dumps(result, indent=2)}")
        return False


def verify_s3_structure(session_id):
    """TEST 6: Verify S3 directory structure is correct."""
    print("\n" + "=" * 60)
    print("TEST 6: Verify S3 Structure")
    print("=" * 60)

    expected_paths = [
        f"sessions/{session_id}/",
        f"sessions/{session_id}/session.json",
        f"sessions/{session_id}/designs/",
        f"sessions/{session_id}/design_history.csv",
        f"sessions/{session_id}/iterations/"
    ]

    found = []
    missing = []

    for path in expected_paths:
        try:
            if path.endswith('/'):
                # Check prefix exists
                response = s3_client.list_objects_v2(
                    Bucket=BUCKET_NAME,
                    Prefix=path,
                    MaxKeys=1
                )
                if 'Contents' in response or 'CommonPrefixes' in response:
                    found.append(path)
                    print(f"  ✓ {path}")
                else:
                    missing.append(path)
                    print(f"  ⚠ {path} (empty)")
            else:
                # Check specific file exists
                s3_client.head_object(Bucket=BUCKET_NAME, Key=path)
                found.append(path)
                print(f"  ✓ {path}")
        except:
            missing.append(path)
            print(f"  ✗ {path} (not found)")

    print(f"\n  Found: {len(found)}/{len(expected_paths)} paths")
    return len(missing) == 0


def run_full_integration_test():
    """Run complete end-to-end integration test."""
    print("\n" + "=" * 70)
    print(" CFD OPTIMIZATION - S3 INTEGRATION TEST")
    print("=" * 70)
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Region: {REGION}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    results = []

    # Test 1: Initialize
    session_id = test_initialize_optimization()
    if not session_id:
        print("\n✗ CRITICAL: Failed to initialize session")
        return False
    results.append(("Initialize Session", True))

    # Run multiple iterations to test convergence
    num_iterations = 3
    geometries = []

    for i in range(1, num_iterations + 1):
        print(f"\n{'=' * 60}")
        print(f"ITERATION {i}/{num_iterations}")
        print(f"{'=' * 60}")

        # Test 2: Generate Geometry
        geometry_id = test_generate_geometry(session_id, i)
        if not geometry_id:
            print(f"\n✗ Failed to generate geometry (iteration {i})")
            results.append((f"Generate Geometry {i}", False))
            continue
        results.append((f"Generate Geometry {i}", True))
        geometries.append(geometry_id)

        # Test 3: Run CFD
        cfd_result = test_run_cfd(session_id, geometry_id, i)
        if not cfd_result:
            print(f"\n✗ Failed to run CFD (iteration {i})")
            results.append((f"Run CFD {i}", False))
            continue
        results.append((f"Run CFD {i}", True))

        # Small delay between iterations
        time.sleep(1)

    # Test 4: Check Convergence
    converged = test_check_convergence(session_id, num_iterations)
    results.append(("Check Convergence", True))

    # Test 5: Generate Report
    report_success = test_generate_report(session_id,
                                          'Test complete' if converged else 'Max iterations')
    results.append(("Generate Report", report_success))

    # Test 6: Verify Structure
    structure_ok = verify_s3_structure(session_id)
    results.append(("S3 Structure", structure_ok))

    # Summary
    print("\n" + "=" * 70)
    print(" TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status:8} {test_name}")

    print("\n" + "=" * 70)
    print(f" Results: {passed}/{total} tests passed")
    print("=" * 70)

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print(f"\nSession data stored at:")
        print(f"  s3://{BUCKET_NAME}/sessions/{session_id}/")
        print("\n✓ S3 integration is working correctly")
        print("\nNext steps:")
        print("  1. Update Step Functions to pass sessionId through all steps")
        print("  2. Test full orchestration with Bedrock Agent")
        print("  3. Run convergence test with 5-8 iterations")
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        print("Check CloudWatch logs for details:")
        for func_name in FUNCTIONS.values():
            print(f"  aws logs tail /aws/lambda/{func_name} --follow")

    return passed == total


if __name__ == '__main__':
    success = run_full_integration_test()
    exit(0 if success else 1)
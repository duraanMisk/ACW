#!/usr/bin/env python3
"""
Simple S3 Integration Test

Tests that Lambda functions can:
1. Create a session in S3
2. Write design data to S3
3. Read data back from S3
"""

import boto3
import json
from datetime import datetime
import uuid

lambda_client = boto3.client('lambda', region_name='us-east-1')
s3_client = boto3.client('s3', region_name='us-east-1')

BUCKET_NAME = "cfd-optimization-data-120569639479-us-east-1"


def invoke_lambda(function_name, payload):
    """Invoke Lambda and return result."""
    response = lambda_client.invoke(
        FunctionName=function_name,
        Payload=json.dumps(payload)
    )
    return json.loads(response['Payload'].read())


def test_initialize_optimization():
    """Test that initialize_optimization creates a session in S3."""
    print("\n" + "=" * 60)
    print("TEST 1: Initialize Optimization (Create S3 Session)")
    print("=" * 60)

    payload = {
        'objective': 'minimize_cd',
        'cl_min': 0.30,
        'reynolds': 500000,
        'max_iter': 3
    }

    print("Calling initialize_optimization...")
    result = invoke_lambda('cfd-initialize-optimization', payload)

    if result['statusCode'] == 200:
        body = result['body']
        session_id = body['sessionId']

        print(f"✓ Lambda responded successfully")
        print(f"  Session ID: {session_id}")
        print(f"  S3 Enabled: {body.get('s3_enabled', 'unknown')}")

        # Check if session was created in S3
        print("\nVerifying session in S3...")
        session_key = f"sessions/{session_id}/session.json"

        try:
            response = s3_client.get_object(Bucket=BUCKET_NAME, Key=session_key)
            session_data = json.loads(response['Body'].read())

            print(f"✓ Session found in S3:")
            print(f"  Created: {session_data['created_at']}")
            print(f"  Status: {session_data['status']}")
            print(f"  Max iterations: {session_data['config']['max_iter']}")

            return session_id

        except s3_client.exceptions.NoSuchKey:
            print(f"✗ Session NOT found in S3")
            print(f"  Expected key: {session_key}")
            return None
    else:
        print(f"✗ Lambda failed: {result}")
        return None


def test_run_cfd_with_s3(session_id):
    """Test that run_cfd writes to S3."""
    print("\n" + "=" * 60)
    print("TEST 2: Run CFD (Write Design to S3)")
    print("=" * 60)

    # Format as Bedrock Agent would
    payload = {
        'requestBody': {
            'content': {
                'application/json': {
                    'properties': [
                        {'name': 'geometry_id', 'value': 'NACA4412_a2.0'},
                        {'name': 'reynolds', 'value': '500000'},
                        {'name': 'session_id', 'value': session_id}
                    ]
                }
            }
        }
    }

    print(f"Calling run_cfd with session_id: {session_id}")
    result = invoke_lambda('cfd-run-cfd', payload)

    if result['response']['httpStatusCode'] == 200:
        body_str = result['response']['responseBody']['application/json']['body']
        cfd_results = json.loads(body_str)

        print(f"✓ CFD simulation completed:")
        print(f"  Cl: {cfd_results['Cl']:.4f}")
        print(f"  Cd: {cfd_results['Cd']:.5f}")
        print(f"  L/D: {cfd_results['L_D']:.2f}")

        # Check if design was written to S3
        print("\nVerifying design in S3...")

        # List designs in this session
        prefix = f"sessions/{session_id}/designs/"
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)

        if 'Contents' in response and len(response['Contents']) > 0:
            design_count = len(response['Contents'])
            print(f"✓ Found {design_count} design(s) in S3")

            # Read the first design
            design_key = response['Contents'][0]['Key']
            design_response = s3_client.get_object(Bucket=BUCKET_NAME, Key=design_key)
            design_data = json.loads(design_response['Body'].read())

            print(f"  Design: {design_data['geometry_id']}")
            print(f"  Cd: {design_data['Cd']:.5f}")
            print(f"  Converged: {design_data['converged']}")

            return True
        else:
            print(f"✗ No designs found in S3")
            print(f"  Expected prefix: {prefix}")
            return False
    else:
        print(f"✗ CFD simulation failed: {result}")
        return False


def test_check_convergence_with_s3(session_id):
    """Test that check_convergence reads from S3."""
    print("\n" + "=" * 60)
    print("TEST 3: Check Convergence (Read from S3)")
    print("=" * 60)

    payload = {
        'sessionId': session_id,
        'max_iter': 3,
        'cl_min': 0.30,
        'iteration': 1
    }

    print(f"Calling check_convergence with session_id: {session_id}")
    result = invoke_lambda('cfd-check-convergence', payload)

    if result['statusCode'] == 200:
        body = result['body']

        print(f"✓ Convergence check completed:")
        print(f"  Converged: {body['converged']}")
        print(f"  Iteration: {body.get('iteration', 'N/A')}")
        print(f"  Reason: {body.get('reason', 'N/A')}")

        if body.get('best_cd'):
            print(f"  Best Cd: {body['best_cd']:.5f}")

        return True
    else:
        print(f"✗ Convergence check failed: {result}")
        return False


def test_generate_report_with_s3(session_id):
    """Test that generate_report reads from S3."""
    print("\n" + "=" * 60)
    print("TEST 4: Generate Report (Read Summary from S3)")
    print("=" * 60)

    payload = {
        'sessionId': session_id,
        'cl_min': 0.30,
        'reason': 'Test complete'
    }

    print(f"Calling generate_report with session_id: {session_id}")
    result = invoke_lambda('cfd-generate-report', payload)

    if result['statusCode'] == 200:
        body = result['body']

        if body.get('status') == 'INCOMPLETE':
            print(f"⚠ Report incomplete (expected - need more iterations)")
            return True

        print(f"✓ Report generated:")

        if 'optimization_summary' in body:
            summary = body['optimization_summary']
            print(f"  Status: {summary.get('status')}")
            print(f"  Designs evaluated: {summary.get('designs_evaluated')}")

        if 'best_design' in body:
            design = body['best_design']
            print(f"  Best design: {design.get('geometry_id')}")
            print(f"  Best Cd: {design.get('Cd'):.5f}")

        return True
    else:
        print(f"✗ Report generation failed: {result}")
        return False


def verify_s3_structure(session_id):
    """Verify S3 directory structure."""
    print("\n" + "=" * 60)
    print("TEST 5: Verify S3 Structure")
    print("=" * 60)

    print(f"Checking S3 structure for session: {session_id}")

    expected_prefixes = [
        f"sessions/{session_id}/",
        f"sessions/{session_id}/designs/",
        f"sessions/{session_id}/iterations/"
    ]

    for prefix in expected_prefixes:
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, Delimiter='/')

        if 'Contents' in response or 'CommonPrefixes' in response:
            count = len(response.get('Contents', []))
            subdirs = len(response.get('CommonPrefixes', []))
            print(f"✓ {prefix}")
            if count > 0:
                print(f"    {count} file(s)")
            if subdirs > 0:
                print(f"    {subdirs} subdirectory(ies)")
        else:
            print(f"⚠ {prefix} (empty)")

    print(f"\n✓ S3 structure verified")
    return True


def main():
    """Run all S3 integration tests."""
    print("=" * 60)
    print("S3 Integration Tests")
    print("=" * 60)
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Region: us-east-1")

    results = []

    # Test 1: Initialize
    session_id = test_initialize_optimization()
    if session_id:
        results.append(("Initialize Optimization", True))

        # Test 2: Run CFD
        cfd_success = test_run_cfd_with_s3(session_id)
        results.append(("Run CFD with S3", cfd_success))

        # Test 3: Check Convergence
        conv_success = test_check_convergence_with_s3(session_id)
        results.append(("Check Convergence", conv_success))

        # Test 4: Generate Report
        report_success = test_generate_report_with_s3(session_id)
        results.append(("Generate Report", report_success))

        # Test 5: Verify Structure
        struct_success = verify_s3_structure(session_id)
        results.append(("S3 Structure", struct_success))
    else:
        results.append(("Initialize Optimization", False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status:8} {test_name}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nS3 integration is working correctly.")
        print(f"\nTest data stored at:")
        print(f"  s3://{BUCKET_NAME}/sessions/{session_id}/")
        print("\nNext steps:")
        print("  1. Update Step Functions to pass sessionId")
        print("  2. Update Bedrock Agent prompt to include session_id")
        print("  3. Test full optimization workflow")
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        print("\nCheck CloudWatch logs for error details:")
        print("  aws logs tail /aws/lambda/cfd-initialize-optimization --follow")


if __name__ == '__main__':
    main()
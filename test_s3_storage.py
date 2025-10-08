#!/usr/bin/env python3
"""
Test S3 storage integration.

This script verifies that:
1. Lambda functions can write to S3
2. Data persists across Lambda invocations
3. CLI can read data from S3
"""

import boto3
import json
import time
from datetime import datetime


def get_bucket_name():
    """Get S3 bucket name from CloudFormation."""
    cf = boto3.client('cloudformation', region_name='us-east-1')
    response = cf.describe_stacks(StackName='CFDOptimizationStorageStack')
    outputs = response['Stacks'][0]['Outputs']

    for output in outputs:
        if output['OutputKey'] == 'ResultsBucketName':
            return output['OutputValue']

    raise Exception("Bucket name not found")


def test_run_cfd_writes_to_s3(bucket_name):
    """Test that run_cfd Lambda writes design history to S3."""
    print("\n" + "=" * 60)
    print("TEST 1: run_cfd writes to S3")
    print("=" * 60)

    lambda_client = boto3.client('lambda', region_name='us-east-1')
    s3_client = boto3.client('s3', region_name='us-east-1')

    # Generate unique session ID
    session_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Invoke run_cfd Lambda
    print(f"📞 Invoking run_cfd with session_id: {session_id}")

    payload = {
        "apiPath": "/run_cfd",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "geometry_id", "value": "NACA4412_a2.0"},
                        {"name": "reynolds", "value": "500000"},
                        {"name": "alpha", "value": "2.0"}
                    ]
                }
            }
        },
        "SESSION_ID": session_id  # Pass session ID
    }

    response = lambda_client.invoke(
        FunctionName='cfd-run-cfd',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )

    result = json.loads(response['Payload'].read())
    print(f"✅ Lambda invoked successfully")
    print(f"   Response: {result}")

    # Wait a moment for S3 write
    print("⏳ Waiting for S3 write...")
    time.sleep(2)

    # Check S3 for design_history.csv
    s3_key = f"{session_id}/design_history.csv"
    print(f"🔍 Checking S3 for: {s3_key}")

    try:
        obj = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        content = obj['Body'].read().decode('utf-8')
        print(f"✅ File found in S3!")
        print(f"   Content preview:\n{content[:200]}...")
        return True
    except s3_client.exceptions.NoSuchKey:
        print(f"❌ File not found in S3")
        print(f"   Bucket: {bucket_name}")
        print(f"   Key: {s3_key}")
        return False


def test_cli_can_read_from_s3(bucket_name):
    """Test that CLI can read data from S3."""
    print("\n" + "=" * 60)
    print("TEST 2: CLI reads from S3")
    print("=" * 60)

    s3_client = boto3.client('s3', region_name='us-east-1')

    # List all sessions
    print(f"📋 Listing sessions in bucket: {bucket_name}")

    response = s3_client.list_objects_v2(
        Bucket=bucket_name,
        Delimiter='/'
    )

    if 'CommonPrefixes' not in response:
        print("❌ No sessions found in S3")
        return False

    sessions = [prefix['Prefix'].rstrip('/') for prefix in response['CommonPrefixes']]
    print(f"✅ Found {len(sessions)} session(s):")
    for session in sessions:
        print(f"   - {session}")

    # Read the most recent session
    latest_session = sessions[-1]
    print(f"\n📖 Reading data from session: {latest_session}")

    # Read design_history.csv
    try:
        obj = s3_client.get_object(
            Bucket=bucket_name,
            Key=f"{latest_session}/design_history.csv"
        )
        content = obj['Body'].read().decode('utf-8')
        lines = content.split('\n')
        print(f"✅ design_history.csv found ({len(lines)} lines)")
        print(f"   Headers: {lines[0]}")
        if len(lines) > 1:
            print(f"   First row: {lines[1]}")
        return True
    except Exception as e:
        print(f"❌ Failed to read design_history.csv: {e}")
        return False


def test_data_persistence():
    """Test that data persists across Lambda invocations."""
    print("\n" + "=" * 60)
    print("TEST 3: Data persistence")
    print("=" * 60)

    lambda_client = boto3.client('lambda', region_name='us-east-1')
    s3_client = boto3.client('s3', region_name='us-east-1')
    bucket_name = get_bucket_name()

    # Use same session ID for multiple invocations
    session_id = f"persist-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print(f"📞 Running 3 CFD simulations with session_id: {session_id}")

    test_cases = [
        ("NACA4412_a2.0", 2.0),
        ("NACA4410_a2.5", 2.5),
        ("NACA4310_a3.0", 3.0),
    ]

    for geometry_id, alpha in test_cases:
        payload = {
            "apiPath": "/run_cfd",
            "requestBody": {
                "content": {
                    "application/json": {
                        "properties": [
                            {"name": "geometry_id", "value": geometry_id},
                            {"name": "reynolds", "value": "500000"},
                            {"name": "alpha", "value": str(alpha)}
                        ]
                    }
                }
            },
            "SESSION_ID": session_id
        }

        lambda_client.invoke(
            FunctionName='cfd-run-cfd',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        print(f"   ✅ {geometry_id} completed")
        time.sleep(1)

    # Wait for final S3 write
    time.sleep(2)

    # Check that all 3 designs are in the CSV
    s3_key = f"{session_id}/design_history.csv"
    obj = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
    content = obj['Body'].read().decode('utf-8')
    lines = content.strip().split('\n')

    # Should have header + 3 data rows
    expected_lines = 4
    actual_lines = len(lines)

    print(f"\n📊 Results:")
    print(f"   Expected rows: {expected_lines} (1 header + 3 data)")
    print(f"   Actual rows: {actual_lines}")

    if actual_lines == expected_lines:
        print(f"✅ All designs persisted correctly!")
        return True
    else:
        print(f"❌ Row count mismatch")
        print(f"   Content:\n{content}")
        return False


def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║          S3 Storage Integration Test Suite                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)

    # Get bucket name
    try:
        bucket_name = get_bucket_name()
        print(f"✅ Found S3 bucket: {bucket_name}")
    except Exception as e:
        print(f"❌ Failed to get bucket name: {e}")
        print("   Make sure CFDOptimizationStorageStack is deployed")
        return

    # Run tests
    results = []

    results.append(("run_cfd writes to S3", test_run_cfd_writes_to_s3(bucket_name)))
    results.append(("CLI reads from S3", test_cli_can_read_from_s3(bucket_name)))
    results.append(("Data persistence", test_data_persistence()))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✨ All tests passed! S3 integration is working correctly.")
        print("\nYou can now proceed with CLI development (Phase 2)")
    else:
        print("\n⚠️  Some tests failed. Check the logs above for details.")


if __name__ == "__main__":
    main()
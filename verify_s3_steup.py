#!/usr/bin/env python3
"""
Verify S3 Setup

Checks all prerequisites before deploying Lambda functions:
1. S3 bucket exists and is accessible
2. Lambda role has S3 permissions
3. Shared files exist
4. Lambda functions exist
"""

import boto3
import json
import os

REGION = 'us-east-1'
ACCOUNT_ID = '120569639479'
BUCKET_NAME = f'cfd-optimization-data-{ACCOUNT_ID}'
LAMBDA_ROLE_ARN = 'arn:aws:iam::120569639479:role/CFDOptimizationAgentStack-LambdaExecutionRoleC61CE2F-l2R78aFnANAv'

s3_client = boto3.client('s3', region_name=REGION)
iam_client = boto3.client('iam', region_name=REGION)
lambda_client = boto3.client('lambda', region_name=REGION)


def check_s3_bucket():
    """Check if S3 bucket exists and is accessible."""
    print("\n" + "=" * 60)
    print("CHECK 1: S3 Bucket")
    print("=" * 60)

    try:
        # Check if bucket exists
        s3_client.head_bucket(Bucket=BUCKET_NAME)
        print(f"✓ Bucket exists: {BUCKET_NAME}")

        # Try to list objects (test permissions)
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, MaxKeys=1)
        print(f"✓ List permission: OK")

        # Try to write a test file
        test_key = 'test/verify_setup.json'
        test_data = {'test': 'verification', 'timestamp': '2025-10-14'}

        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=test_key,
            Body=json.dumps(test_data),
            ContentType='application/json'
        )
        print(f"✓ Write permission: OK")

        # Try to read it back
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=test_key)
        data = json.loads(response['Body'].read())
        print(f"✓ Read permission: OK")

        # Clean up
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=test_key)
        print(f"✓ Delete permission: OK")

        print(f"\n✓ S3 bucket is fully accessible")
        return True

    except Exception as e:
        print(f"\n✗ S3 bucket check FAILED: {e}")
        return False


def check_lambda_role_permissions():
    """Check if Lambda role has S3 permissions."""
    print("\n" + "=" * 60)
    print("CHECK 2: Lambda Role S3 Permissions")
    print("=" * 60)

    role_name = LAMBDA_ROLE_ARN.split('/')[-1]
    print(f"Role: {role_name}")

    try:
        # Get all inline policies
        print("\nChecking inline policies...")
        response = iam_client.list_role_policies(RoleName=role_name)
        policy_names = response['PolicyNames']

        print(f"Found {len(policy_names)} inline policies:")
        for policy_name in policy_names:
            print(f"  - {policy_name}")

        # Check for S3 policy
        s3_policy_found = False
        for policy_name in policy_names:
            policy_response = iam_client.get_role_policy(
                RoleName=role_name,
                PolicyName=policy_name
            )
            policy_doc = json.loads(policy_response['PolicyDocument'])

            # Check if policy has S3 permissions
            for statement in policy_doc.get('Statement', []):
                actions = statement.get('Action', [])
                if isinstance(actions, str):
                    actions = [actions]

                # Check for S3 actions
                s3_actions = [a for a in actions if a.startswith('s3:')]
                if s3_actions:
                    print(f"\n✓ Found S3 permissions in policy: {policy_name}")
                    print(f"  Actions: {', '.join(s3_actions)}")

                    # Check resources
                    resources = statement.get('Resource', [])
                    if isinstance(resources, str):
                        resources = [resources]

                    bucket_resources = [r for r in resources if BUCKET_NAME in r]
                    if bucket_resources:
                        print(f"  ✓ Permissions apply to bucket: {BUCKET_NAME}")
                        s3_policy_found = True
                    else:
                        print(f"  ⚠ Warning: Permissions don't include bucket {BUCKET_NAME}")
                        print(f"  Resources: {resources}")

        if s3_policy_found:
            print(f"\n✓ Lambda role has S3 permissions for bucket")
            return True
        else:
            print(f"\n✗ Lambda role missing S3 permissions for bucket {BUCKET_NAME}")
            print(f"\nRequired permissions:")
            print(f"  - s3:PutObject")
            print(f"  - s3:GetObject")
            print(f"  - s3:DeleteObject")
            print(f"  - s3:ListBucket")
            return False

    except Exception as e:
        print(f"\n✗ Role permission check FAILED: {e}")
        return False


def check_shared_files():
    """Check if shared files exist."""
    print("\n" + "=" * 60)
    print("CHECK 3: Shared Files")
    print("=" * 60)

    required_files = [
        'lambdas/shared/storage_s3.py',
        'lambdas/shared/session_manager.py'
    ]

    all_exist = True
    for file_path in required_files:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            print(f"✓ {file_path} ({size:,} bytes)")
        else:
            print(f"✗ {file_path} - NOT FOUND")
            all_exist = False

    if all_exist:
        print(f"\n✓ All shared files exist")
        return True
    else:
        print(f"\n✗ Missing shared files")
        print(f"\nCreate these files from the artifacts provided:")
        print(f"  1. storage_s3.py - S3 storage adapter")
        print(f"  2. session_manager.py - Session management")
        return False


def check_lambda_functions():
    """Check if Lambda functions exist."""
    print("\n" + "=" * 60)
    print("CHECK 4: Lambda Functions")
    print("=" * 60)

    required_functions = [
        'cfd-generate-geometry',
        'cfd-run-cfd',
        'cfd-get-next-candidates',
        'cfd-initialize-optimization',
        'cfd-check-convergence',
        'cfd-generate-report',
        'cfd-invoke-bedrock-agent'
    ]

    all_exist = True
    for function_name in required_functions:
        try:
            response = lambda_client.get_function(FunctionName=function_name)
            config = response['Configuration']
            runtime = config['Runtime']
            version = config['Version']

            # Check environment variables
            env_vars = config.get('Environment', {}).get('Variables', {})
            has_s3_bucket = 'S3_BUCKET' in env_vars

            status = "✓" if has_s3_bucket else "⚠"
            print(f"{status} {function_name}")
            print(f"    Runtime: {runtime}, Version: {version}")
            if has_s3_bucket:
                print(f"    S3_BUCKET: {env_vars['S3_BUCKET']}")
            else:
                print(f"    ⚠ Missing S3_BUCKET env var")

        except lambda_client.exceptions.ResourceNotFoundException:
            print(f"✗ {function_name} - NOT FOUND")
            all_exist = False

    if all_exist:
        print(f"\n✓ All Lambda functions exist")
        return True
    else:
        print(f"\n✗ Some Lambda functions missing")
        return False


def check_handler_files():
    """Check if handler files have been updated."""
    print("\n" + "=" * 60)
    print("CHECK 5: Updated Handler Files")
    print("=" * 60)

    handlers = [
        'lambdas/generate_geometry/handler.py',
        'lambdas/run_cfd/handler.py',
        'lambdas/get_next_candidates/handler.py',
        'lambdas/initialize_optimization/handler.py',
        'lambdas/check_convergence/handler.py',
        'lambdas/generate_report/handler.py',
        'lambdas/invoke_bedrock_agent/handler.py'
    ]

    all_updated = True
    for handler_path in handlers:
        if not os.path.exists(handler_path):
            print(f"✗ {handler_path} - NOT FOUND")
            all_updated = False
            continue

        # Check if file contains S3 imports
        with open(handler_path, 'r') as f:
            content = f.read()
            has_s3_import = 'storage_s3' in content or 'session_manager' in content
            has_session_id = 'session_id' in content.lower()

            if has_s3_import and has_session_id:
                print(f"✓ {handler_path}")
            else:
                print(f"⚠ {handler_path}")
                if not has_s3_import:
                    print(f"    Missing S3 storage imports")
                if not has_session_id:
                    print(f"    Missing session_id handling")
                all_updated = False

    if all_updated:
        print(f"\n✓ All handlers updated for S3 storage")
        return True
    else:
        print(f"\n⚠ Some handlers need updating")
        print(f"\nUpdate handlers with the provided artifacts")
        return False


def main():
    """Run all checks."""
    print("=" * 60)
    print("S3 Setup Verification")
    print("=" * 60)
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Region: {REGION}")

    results = []

    # Run all checks
    results.append(("S3 Bucket", check_s3_bucket()))
    results.append(("Lambda Role Permissions", check_lambda_role_permissions()))
    results.append(("Shared Files", check_shared_files()))
    results.append(("Lambda Functions", check_lambda_functions()))
    results.append(("Handler Files", check_handler_files()))

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for check_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:8} {check_name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)

    if all_passed:
        print("✓ ALL CHECKS PASSED!")
        print("=" * 60)
        print("\nReady to deploy:")
        print("  python deploy_updated_lambdas.py")
    else:
        print("⚠ SOME CHECKS FAILED")
        print("=" * 60)
        print("\nFix the issues above before deploying.")
        print("\nCommon issues:")
        print("  1. Missing shared files → Copy storage_s3.py and session_manager.py")
        print("  2. Missing S3 permissions → Wait 1-2 minutes for IAM propagation")
        print("  3. Handlers not updated → Replace with provided artifacts")


if __name__ == '__main__':
    main()
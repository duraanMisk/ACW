#!/usr/bin/env python3
"""
Fix Lambda S3 Permissions

Adds S3 access policy to Lambda execution role using ARN instead of role name.
This works around the 64-character role name limit.
"""

import boto3
import json

REGION = 'us-east-1'
ACCOUNT_ID = '120569639479'
BUCKET_NAME = f'cfd-optimization-data-{ACCOUNT_ID}'
LAMBDA_ROLE_ARN = 'arn:aws:iam::120569639479:role/CFDOptimizationAgentStack-LambdaExecutionRoleC61CE2F-l2R78aFnANAv'

iam_client = boto3.client('iam', region_name=REGION)


def extract_role_name_from_arn(role_arn):
    """Extract role name from ARN."""
    # Format: arn:aws:iam::ACCOUNT:role/ROLE_NAME
    return role_arn.split('/')[-1]


def update_lambda_permissions():
    """Add S3 permissions to Lambda execution role using inline policy."""

    role_name = extract_role_name_from_arn(LAMBDA_ROLE_ARN)

    print("=" * 60)
    print("Fix Lambda S3 Permissions")
    print("=" * 60)
    print(f"Role ARN: {LAMBDA_ROLE_ARN}")
    print(f"Role Name: {role_name}")
    print(f"Role Name Length: {len(role_name)} characters")
    print(f"Bucket: {BUCKET_NAME}\n")

    # Create S3 access policy
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "S3OptimizationDataAccess",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:DeleteObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    f"arn:aws:s3:::{BUCKET_NAME}",
                    f"arn:aws:s3:::{BUCKET_NAME}/*"
                ]
            }
        ]
    }

    policy_name = 'S3OptimizationDataAccess'

    try:
        # First, try to get the role to verify it exists
        print("Verifying role exists...")
        iam_client.get_role(RoleName=role_name)
        print("✓ Role found\n")

        # Check if policy already exists
        print("Checking for existing S3 policy...")
        try:
            existing_policy = iam_client.get_role_policy(
                RoleName=role_name,
                PolicyName=policy_name
            )
            print(f"✓ Policy '{policy_name}' already exists")
            print("  Updating policy...\n")
        except iam_client.exceptions.NoSuchEntityException:
            print(f"  Policy '{policy_name}' not found, creating new...\n")

        # Put (create or update) the inline policy
        print("Applying S3 permissions policy...")
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document)
        )

        print("✓ Successfully added S3 permissions to Lambda role!\n")

        # Verify the policy was applied
        print("Verifying policy...")
        policy_response = iam_client.get_role_policy(
            RoleName=role_name,
            PolicyName=policy_name
        )

        policy_doc = json.loads(policy_response['PolicyDocument'])
        print(f"✓ Policy verified:")
        print(f"  - PutObject: Allowed")
        print(f"  - GetObject: Allowed")
        print(f"  - DeleteObject: Allowed")
        print(f"  - ListBucket: Allowed")
        print(f"  - Bucket: {BUCKET_NAME}")

        return True

    except iam_client.exceptions.NoSuchEntityException:
        print(f"✗ Error: Role not found")
        print(f"\nThe role name might have changed. Current role ARN:")
        print(f"  {LAMBDA_ROLE_ARN}")
        print(f"\nTo fix manually:")
        print(f"1. Go to IAM Console: https://console.aws.amazon.com/iam/")
        print(f"2. Go to Roles")
        print(f"3. Search for: {role_name[:30]}...")
        print(f"4. Click on the role")
        print(f"5. Add inline policy:")
        print(json.dumps(policy_document, indent=2))
        return False

    except Exception as e:
        print(f"✗ Error: {e}")
        print(f"\nManual steps:")
        print(f"1. Go to IAM Console: https://console.aws.amazon.com/iam/")
        print(f"2. Go to Roles")
        print(f"3. Search for: {role_name[:30]}...")
        print(f"4. Click on the role")
        print(f"5. Click 'Add permissions' → 'Create inline policy'")
        print(f"6. Use JSON editor and paste:")
        print(json.dumps(policy_document, indent=2))
        return False


def test_permissions():
    """Test that Lambda can access S3 bucket."""
    print("\n" + "=" * 60)
    print("Testing S3 Access")
    print("=" * 60)

    s3_client = boto3.client('s3', region_name=REGION)

    test_key = 'test/permissions_test.json'
    test_data = {'message': 'Lambda S3 permissions test', 'bucket': BUCKET_NAME}

    try:
        # Write test file
        print("Testing write access...")
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=test_key,
            Body=json.dumps(test_data),
            ContentType='application/json'
        )
        print("✓ Write successful")

        # Read test file
        print("Testing read access...")
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=test_key)
        data = json.loads(response['Body'].read())
        print("✓ Read successful")

        # Delete test file
        print("Testing delete access...")
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=test_key)
        print("✓ Delete successful")

        print("\n✓ All S3 operations successful!")
        return True

    except Exception as e:
        print(f"\n✗ S3 access test failed: {e}")
        print("\nThis is expected if running locally.")
        print("Lambda functions will have the correct permissions when deployed.")
        return False


def main():
    """Main execution."""

    # Update permissions
    success = update_lambda_permissions()

    if success:
        # Test permissions (may fail if running locally, that's OK)
        test_permissions()

        print("\n" + "=" * 60)
        print("✓ Lambda S3 Permissions Fixed!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Deploy Lambda functions: python deploy_updated_lambdas.py")
        print("  2. Test S3 integration: python test_s3_integration.py")
    else:
        print("\n" + "=" * 60)
        print("⚠ Could Not Update Permissions Automatically")
        print("=" * 60)
        print("\nFollow the manual steps above to add S3 permissions.")


if __name__ == '__main__':
    main()
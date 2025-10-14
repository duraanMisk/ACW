#!/usr/bin/env python3
"""
Create S3 bucket for CFD optimization data storage.
"""

import boto3
import json

REGION = 'us-east-1'
ACCOUNT_ID = '120569639479'
BUCKET_NAME = f'cfd-optimization-data-{ACCOUNT_ID}'

s3_client = boto3.client('s3', region_name=REGION)
iam_client = boto3.client('iam', region_name=REGION)


def create_bucket():
    """Create S3 bucket if it doesn't exist."""
    try:
        # Check if bucket exists
        s3_client.head_bucket(Bucket=BUCKET_NAME)
        print(f"✓ Bucket {BUCKET_NAME} already exists")
        return True
    except:
        pass

    try:
        # Create bucket
        if REGION == 'us-east-1':
            s3_client.create_bucket(Bucket=BUCKET_NAME)
        else:
            s3_client.create_bucket(
                Bucket=BUCKET_NAME,
                CreateBucketConfiguration={'LocationConstraint': REGION}
            )

        print(f"✓ Created bucket {BUCKET_NAME}")

        # Enable versioning
        s3_client.put_bucket_versioning(
            Bucket=BUCKET_NAME,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        print(f"✓ Enabled versioning")

        # Set lifecycle policy to delete old data after 90 days
        lifecycle_policy = {
            'Rules': [
                {
                    'ID': 'DeleteOldSessions',
                    'Status': 'Enabled',
                    'Prefix': 'sessions/',
                    'Expiration': {'Days': 90}
                }
            ]
        }

        s3_client.put_bucket_lifecycle_configuration(
            Bucket=BUCKET_NAME,
            LifecycleConfiguration=lifecycle_policy
        )
        print(f"✓ Set lifecycle policy (90 day retention)")

        return True

    except Exception as e:
        print(f"✗ Failed to create bucket: {e}")
        return False


def update_lambda_permissions():
    """Add S3 permissions to Lambda execution role."""

    LAMBDA_ROLE_NAME = 'CFDOptimizationAgentStack-LambdaExecutionRoleC61CE2F-l2R78aFnANAv'

    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
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

    try:
        # Try to update inline policy
        iam_client.put_role_policy(
            RoleName=LAMBDA_ROLE_NAME,
            PolicyName='S3OptimizationDataAccess',
            PolicyDocument=json.dumps(policy_document)
        )
        print(f"✓ Added S3 permissions to Lambda role")
        return True

    except Exception as e:
        print(f"⚠ Could not update Lambda role automatically: {e}")
        print(f"\nManual steps:")
        print(f"1. Go to IAM Console")
        print(f"2. Find role: {LAMBDA_ROLE_NAME}")
        print(f"3. Add inline policy with S3 permissions for bucket {BUCKET_NAME}")
        return False


def test_bucket():
    """Test bucket access by writing a test file."""
    test_key = 'test/test.json'
    test_data = {'message': 'S3 bucket is working!'}

    try:
        # Write test file
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=test_key,
            Body=json.dumps(test_data),
            ContentType='application/json'
        )

        # Read it back
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=test_key)
        data = json.loads(response['Body'].read())

        # Delete test file
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=test_key)

        print(f"✓ Bucket read/write test passed")
        return True

    except Exception as e:
        print(f"✗ Bucket test failed: {e}")
        return False


def main():
    print("=" * 60)
    print("CFD Optimization - S3 Storage Setup")
    print("=" * 60)
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Region: {REGION}\n")

    # Step 1: Create bucket
    print("Step 1: Creating S3 bucket...")
    if not create_bucket():
        return

    # Step 2: Update Lambda permissions
    print("\nStep 2: Updating Lambda permissions...")
    update_lambda_permissions()

    # Step 3: Test bucket
    print("\nStep 3: Testing bucket access...")
    if test_bucket():
        print("\n" + "=" * 60)
        print("✓ S3 Storage Setup Complete!")
        print("=" * 60)
        print(f"\nBucket: {BUCKET_NAME}")
        print(f"Region: {REGION}")
        print("\nNext steps:")
        print("  1. Deploy Lambda functions: python deploy_updated_lambdas.py")
        print("  2. Test S3 storage integration")
    else:
        print("\n⚠ Setup complete but bucket test failed")
        print("Check IAM permissions")


if __name__ == '__main__':
    main()
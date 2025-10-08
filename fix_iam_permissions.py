#!/usr/bin/env python3
"""
Add S3 permissions to existing Lambda IAM roles.
This is a quick fix to avoid CDK deployment conflicts.
"""

import boto3
import json


def get_bucket_name():
    """Get S3 bucket name from CloudFormation."""
    cf = boto3.client('cloudformation', region_name='us-east-1')
    response = cf.describe_stacks(StackName='CFDOptimizationStorageStack')
    outputs = response['Stacks'][0]['Outputs']

    for output in outputs:
        if output['OutputKey'] == 'ResultsBucketName':
            return output['OutputValue']

    raise Exception("Bucket name not found")


def get_lambda_role_name(function_name):
    """Get the IAM role name for a Lambda function."""
    lambda_client = boto3.client('lambda', region_name='us-east-1')

    response = lambda_client.get_function(FunctionName=function_name)
    role_arn = response['Configuration']['Role']

    # Extract role name from ARN
    # Format: arn:aws:iam::123456789012:role/RoleName
    role_name = role_arn.split('/')[-1]

    return role_name


def add_s3_permissions(role_name, bucket_name):
    """Add S3 read/write permissions to a role."""
    iam = boto3.client('iam', region_name='us-east-1')

    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:DeleteObject"
                ],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*"
                ]
            }
        ]
    }

    policy_name = "S3OptimizationResultsAccess"

    try:
        # Try to create the policy
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document)
        )
        print(f"✅ Added S3 policy to role: {role_name}")
        return True
    except Exception as e:
        print(f"❌ Failed to add policy: {e}")
        return False


def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║          Fix IAM Permissions for S3 Access                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)

    # Get bucket name
    print("📋 Getting S3 bucket name...")
    bucket_name = get_bucket_name()
    print(f"✅ Bucket: {bucket_name}")

    # Lambda functions that need S3 access
    lambda_functions = [
        'cfd-generate-geometry',
        'cfd-run-cfd',
        'cfd-get-next-candidates',
    ]

    print(f"\n🔧 Updating IAM roles for {len(lambda_functions)} Lambda functions...")

    # Get unique role names (they might share the same role)
    role_names = set()
    for func_name in lambda_functions:
        try:
            role_name = get_lambda_role_name(func_name)
            role_names.add(role_name)
            print(f"  {func_name} → {role_name}")
        except Exception as e:
            print(f"  ⚠️  Failed to get role for {func_name}: {e}")

    # Add S3 permissions to each unique role
    print(f"\n📝 Adding S3 permissions to {len(role_names)} role(s)...")

    success_count = 0
    for role_name in role_names:
        if add_s3_permissions(role_name, bucket_name):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"✨ Updated {success_count}/{len(role_names)} roles successfully!")
    print("=" * 60)

    if success_count == len(role_names):
        print("""
🎉 Success! All Lambda functions now have S3 permissions.

Test it:
  python3 test_s3_storage.py
        """)
    else:
        print("\n⚠️  Some updates failed. Check the errors above.")


if __name__ == "__main__":
    main()
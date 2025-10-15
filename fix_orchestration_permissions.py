# fix_orchestration_permissions.py
import boto3
import json

iam = boto3.client('iam')

ROLE_NAME = 'CFDOptimizationOrchestrat-OrchestrationLambdaRole56-ZJ54hoWEgwgY'
BUCKET_NAME = 'cfd-optimization-data-120569639479-us-east-1'

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
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName='S3OptimizationDataAccess',
        PolicyDocument=json.dumps(policy_document)
    )
    print(f"✓ Added S3 permissions to {ROLE_NAME}")
except Exception as e:
    print(f"✗ Failed: {e}")
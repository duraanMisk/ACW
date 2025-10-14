#!/usr/bin/env python3
"""
Add S3_BUCKET environment variable to all Lambda functions.
"""

import boto3

REGION = 'us-east-1'
ACCOUNT_ID = '120569639479'
BUCKET_NAME = f'cfd-optimization-data-{ACCOUNT_ID}'

lambda_client = boto3.client('lambda', region_name=REGION)

LAMBDA_FUNCTIONS = [
    'cfd-generate-geometry',
    'cfd-run-cfd',
    'cfd-get-next-candidates',
    'cfd-initialize-optimization',
    'cfd-check-convergence',
    'cfd-generate-report',
    'cfd-invoke-bedrock-agent'
]


def update_lambda_env_vars(function_name):
    """Add or update S3_BUCKET environment variable."""
    try:
        # Get current configuration
        response = lambda_client.get_function_configuration(FunctionName=function_name)

        # Get existing environment variables
        current_env = response.get('Environment', {}).get('Variables', {})

        # Add S3_BUCKET
        current_env['S3_BUCKET'] = BUCKET_NAME
        current_env['LOG_LEVEL'] = current_env.get('LOG_LEVEL', 'INFO')

        # Update function configuration
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={'Variables': current_env}
        )

        print(f"✓ {function_name}")
        return True

    except Exception as e:
        print(f"✗ {function_name}: {e}")
        return False


def main():
    print("=" * 60)
    print("Add S3_BUCKET Environment Variable to Lambda Functions")
    print("=" * 60)
    print(f"Bucket: {BUCKET_NAME}\n")

    success_count = 0

    for function_name in LAMBDA_FUNCTIONS:
        if update_lambda_env_vars(function_name):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"Updated: {success_count}/{len(LAMBDA_FUNCTIONS)} functions")
    print("=" * 60)

    if success_count == len(LAMBDA_FUNCTIONS):
        print("\n✓ All Lambda functions updated!")
        print("\nNext: Deploy Lambda code with S3 handlers")
        print("  python deploy_updated_lambdas.py")
    else:
        print(f"\n⚠ {len(LAMBDA_FUNCTIONS) - success_count} function(s) failed")


if __name__ == '__main__':
    main()
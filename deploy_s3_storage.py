#!/usr/bin/env python3
"""
Deploy S3 storage and update Lambda functions.

This script:
1. Deploys the S3 storage stack
2. Updates all Lambda functions with S3-enabled storage.py
3. Adds S3 environment variables to Lambda functions
"""

import subprocess
import sys
import os
import shutil
import zipfile
import boto3
import time
import tempfile
from pathlib import Path


def run_command(cmd, description):
    """Run a shell command and handle errors."""
    print(f"\n{'=' * 60}")
    print(f"🚀 {description}")
    print(f"{'=' * 60}")
    print(f"Command: {cmd}\n")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Error: {description} failed")
        print(f"stderr: {result.stderr}")
        sys.exit(1)

    print(result.stdout)
    print(f"✅ {description} completed successfully")
    return result.stdout


def get_bucket_name():
    """Get the S3 bucket name from CloudFormation outputs."""
    cf = boto3.client('cloudformation', region_name='us-east-1')

    try:
        response = cf.describe_stacks(StackName='CFDOptimizationStorageStack')
        outputs = response['Stacks'][0]['Outputs']

        for output in outputs:
            if output['OutputKey'] == 'ResultsBucketName':
                return output['OutputValue']

        print("❌ Could not find ResultsBucketName in stack outputs")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Error getting bucket name: {e}")
        sys.exit(1)


def update_lambda_package(lambda_name, handler_path, include_storage=True):
    """
    Create deployment package for Lambda function.

    Args:
        lambda_name: Name of Lambda function
        handler_path: Path to handler.py
        include_storage: Whether to include storage.py
    """
    print(f"\n📦 Creating deployment package for {lambda_name}...")

    # Create temporary directory (Windows-compatible)
    import tempfile
    temp_base = Path(tempfile.gettempdir())
    temp_dir = temp_base / f'lambda_deploy_{lambda_name}'
    temp_dir.mkdir(exist_ok=True)

    # Copy handler
    shutil.copy(handler_path, temp_dir / 'handler.py')

    # Copy storage.py if needed
    if include_storage:
        storage_path = Path('lambdas/shared/storage.py')
        if storage_path.exists():
            shutil.copy(storage_path, temp_dir / 'storage.py')
        else:
            print(f"⚠️  Warning: storage.py not found at {storage_path}")

    # Create ZIP file
    zip_path = temp_dir / 'lambda.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in temp_dir.glob('*.py'):
            zipf.write(file, file.name)

    print(f"✅ Package created: {zip_path}")
    return zip_path


def update_lambda_function(lambda_name, zip_path, bucket_name):
    """Update Lambda function code and environment variables."""
    lambda_client = boto3.client('lambda', region_name='us-east-1')

    print(f"\n🔄 Updating {lambda_name}...")

    # Read ZIP file
    with open(zip_path, 'rb') as f:
        zip_content = f.read()

    # Update function code
    try:
        response = lambda_client.update_function_code(
            FunctionName=lambda_name,
            ZipFile=zip_content
        )
        print(f"✅ Code updated (Version: {response['Version']})")
    except Exception as e:
        print(f"❌ Failed to update code: {e}")
        return False

    # Wait for update to complete
    print("⏳ Waiting for update to complete...")
    waiter = lambda_client.get_waiter('function_updated')
    waiter.wait(FunctionName=lambda_name)

    # Update environment variables
    try:
        response = lambda_client.update_function_configuration(
            FunctionName=lambda_name,
            Environment={
                'Variables': {
                    'RESULTS_BUCKET': bucket_name
                }
            }
        )
        print(f"✅ Environment variables updated")
    except Exception as e:
        print(f"❌ Failed to update environment: {e}")
        return False

    return True


def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║       CFD Optimization Agent - S3 Storage Migration       ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)

    # Step 1: Deploy storage stack
    run_command(
        "cd infra/cdk && cdk deploy CFDOptimizationStorageStack --require-approval never",
        "Deploying S3 storage stack"
    )

    # Step 2: Get bucket name
    print("\n📋 Getting S3 bucket name...")
    bucket_name = get_bucket_name()
    print(f"✅ Bucket name: {bucket_name}")

    # Step 3: Update Lambda functions
    lambda_updates = [
        {
            'name': 'cfd-generate-geometry',
            'handler': 'lambdas/generate_geometry/handler.py',
            'storage': True
        },
        {
            'name': 'cfd-run-cfd',
            'handler': 'lambdas/run_cfd/handler.py',
            'storage': True
        },
        {
            'name': 'cfd-get-next-candidates',
            'handler': 'lambdas/get_next_candidates/handler.py',
            'storage': True
        },
        {
            'name': 'cfd-initialize-optimization',
            'handler': 'lambdas/initialize_optimization/handler.py',
            'storage': True
        },
        {
            'name': 'cfd-check-convergence',
            'handler': 'lambdas/check_convergence/handler.py',
            'storage': True
        },
        {
            'name': 'cfd-generate-report',
            'handler': 'lambdas/generate_report/handler.py',
            'storage': True
        },
        {
            'name': 'cfd-invoke-bedrock-agent',
            'handler': 'lambdas/invoke_bedrock_agent/handler.py',
            'storage': False  # This one doesn't need storage.py
        },
    ]

    successful_updates = 0
    failed_updates = []

    for lambda_info in lambda_updates:
        # Create deployment package
        zip_path = update_lambda_package(
            lambda_info['name'],
            lambda_info['handler'],
            lambda_info['storage']
        )

        # Update Lambda function
        success = update_lambda_function(
            lambda_info['name'],
            zip_path,
            bucket_name
        )

        if success:
            successful_updates += 1
        else:
            failed_updates.append(lambda_info['name'])

        # Cleanup temp directory
        if zip_path and zip_path.parent.exists():
            shutil.rmtree(zip_path.parent)

    # Summary
    print("\n" + "=" * 60)
    print("📊 DEPLOYMENT SUMMARY")
    print("=" * 60)
    print(f"✅ Successful updates: {successful_updates}/{len(lambda_updates)}")
    if failed_updates:
        print(f"❌ Failed updates: {', '.join(failed_updates)}")
    print(f"\n🪣 S3 Bucket: {bucket_name}")
    print("\n✨ S3 storage migration complete!")
    print("\nNext steps:")
    print("  1. Test Lambda functions to ensure S3 integration works")
    print("  2. Run a test optimization to verify data persists")
    print("  3. Proceed with CLI development (Phase 2)")


if __name__ == "__main__":
    # Check we're in the right directory
    if not os.path.exists('lambdas'):
        print("❌ Error: Please run this script from the project root directory")
        print("   (The directory containing the 'lambdas' folder)")
        sys.exit(1)

    main()
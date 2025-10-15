# deploy_updated_lambdas.py
"""
Deploy CFD Optimization Lambda Functions with S3 Storage Integration

Handles both:
- UPDATE: Existing functions (tool functions)
- CREATE: New functions (orchestration functions)

Now supports shared files for S3 storage layer.
"""

import boto3
import zipfile
import io
import os
import json
import time

# AWS Configuration
REGION = 'us-east-1'
ACCOUNT_ID = '120569639479'
LAMBDA_ROLE_ARN = 'arn:aws:iam::120569639479:role/CFDOptimizationAgentStack-LambdaExecutionRoleC61CE2F-l2R78aFnANAv'

# Lambda function mappings with shared dependencies
# Format: folder_name -> {'name': aws_function_name, 'shared': [list of shared files]}
LAMBDA_FUNCTIONS = {
    'generate_geometry': {
        'name': 'cfd-generate-geometry',
        'shared': ['storage_s3.py', 'session_manager.py']
    },
    'run_cfd': {
        'name': 'cfd-run-cfd',
        'shared': ['storage_s3.py', 'session_manager.py']
    },
    'get_next_candidates': {
        'name': 'cfd-get-next-candidates',
        'shared': ['storage_s3.py', 'session_manager.py']
    },
    'initialize_optimization': {
        'name': 'cfd-initialize-optimization',
        'shared': ['storage_s3.py', 'session_manager.py']
    },
    'check_convergence': {
        'name': 'cfd-check-convergence',
        'shared': ['storage_s3.py', 'session_manager.py']
    },
    'generate_report': {
        'name': 'cfd-generate-report',
        'shared': ['storage_s3.py', 'session_manager.py']
    },
    'invoke_bedrock_agent': {
        'name': 'cfd-invoke-bedrock-agent',
        'shared': []  # This one might not need S3 storage
    }
}

lambda_client = boto3.client('lambda', region_name=REGION)


def create_deployment_package(function_folder, shared_files=None):
    """
    Create a ZIP file containing the Lambda function code and dependencies.

    Args:
        function_folder: Name of the Lambda function folder
        shared_files: List of shared files to include (optional)

    Returns:
        bytes: ZIP file content
    """
    if shared_files is None:
        shared_files = []

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add handler.py
        handler_path = f'lambdas/{function_folder}/handler.py'
        if os.path.exists(handler_path):
            zip_file.write(handler_path, 'handler.py')
            print(f"  ✓ Added {handler_path}")
        else:
            print(f"  ✗ Warning: {handler_path} not found!")
            return None

        # Add shared files from lambdas/shared/python/  <-- CHANGED THIS
        for shared_file in shared_files:
            # Try the new location first
            shared_path = f'lambdas/shared/python/{shared_file}'
            if os.path.exists(shared_path):
                zip_file.write(shared_path, shared_file)
                print(f"  ✓ Added {shared_path}")
            else:
                # Fall back to old location
                old_shared_path = f'lambdas/shared/{shared_file}'
                if os.path.exists(old_shared_path):
                    zip_file.write(old_shared_path, shared_file)
                    print(f"  ✓ Added {old_shared_path}")
                else:
                    print(f"  ⚠ Warning: {shared_file} not found in either location (skipping)")

    zip_buffer.seek(0)
    return zip_buffer.read()


def function_exists(function_name):
    """
    Check if Lambda function already exists.

    Args:
        function_name: AWS Lambda function name (string)

    Returns:
        bool: True if function exists
    """
    try:
        lambda_client.get_function(FunctionName=function_name)
        return True
    except lambda_client.exceptions.ResourceNotFoundException:
        return False
    except Exception as e:
        print(f"  ✗ Error checking function: {e}")
        return False


def create_function(function_name, zip_content, description):
    """
    Create a new Lambda function.

    Args:
        function_name: AWS Lambda function name
        zip_content: ZIP file bytes
        description: Function description

    Returns:
        bool: True if successful
    """
    try:
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python3.12',
            Role=LAMBDA_ROLE_ARN,
            Handler='handler.lambda_handler',
            Code={'ZipFile': zip_content},
            Description=description,
            Timeout=60,
            MemorySize=512,
            Environment={
                'Variables': {
                    'LOG_LEVEL': 'INFO',
                    'BUCKET_NAME': 'cfd-optimization-data-120569639479-us-east-1'  # Add S3 bucket
                }
            }
        )
        print(f"  ✓ Created function (Version {response['Version']})")
        return True
    except Exception as e:
        print(f"  ✗ Failed to create: {e}")
        return False


def update_function(function_name, zip_content):
    """
    Update existing Lambda function code.

    Args:
        function_name: AWS Lambda function name
        zip_content: ZIP file bytes

    Returns:
        bool: True if successful
    """
    try:
        response = lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_content
        )
        print(f"  ✓ Updated function (Version {response['Version']})")

        # Wait for update to complete
        waiter = lambda_client.get_waiter('function_updated')
        waiter.wait(FunctionName=function_name)

        # Also update environment variables to include S3 bucket
        try:
            lambda_client.update_function_configuration(
                FunctionName=function_name,
                Environment={
                    'Variables': {
                        'LOG_LEVEL': 'INFO',
                        'BUCKET_NAME': 'cfd-optimization-data-120569639479-us-east-1'
                    }
                }
            )
            print(f"  ✓ Updated environment variables")
        except Exception as env_error:
            print(f"  ⚠ Warning: Could not update environment: {env_error}")

        return True
    except Exception as e:
        print(f"  ✗ Failed to update: {e}")
        return False


def main():
    print("=" * 60)
    print("CFD Optimization Lambda Deployment")
    print("=" * 60)
    print(f"AWS Account: {ACCOUNT_ID}")
    print(f"Region: {REGION}\n")

    # Function descriptions
    descriptions = {
        'cfd-generate-geometry': 'Generate airfoil geometry from NACA parameters',
        'cfd-run-cfd': 'Run CFD simulation and return aerodynamic results',
        'cfd-get-next-candidates': 'Propose next optimization candidates',
        'cfd-initialize-optimization': 'Initialize CFD optimization run',
        'cfd-check-convergence': 'Check optimization convergence criteria',
        'cfd-generate-report': 'Generate optimization summary report',
        'cfd-invoke-bedrock-agent': 'Invoke Bedrock Agent wrapper for Step Functions'
    }

    success_count = 0
    total_count = len(LAMBDA_FUNCTIONS)

    for folder_name, config in LAMBDA_FUNCTIONS.items():
        # Extract function name and shared files from config
        if isinstance(config, dict):
            function_name = config['name']
            shared_files = config.get('shared', [])
        else:
            # Backward compatibility: if config is just a string
            function_name = config
            shared_files = []

        print(f"\n{folder_name} → {function_name}")
        print("-" * 60)

        # Create deployment package
        print("Creating deployment package...")
        zip_content = create_deployment_package(folder_name, shared_files)

        if zip_content is None:
            print(f"  ✗ Skipping {function_name} (missing files)")
            continue

        print(f"  Package size: {len(zip_content) / 1024:.1f} KB")

        # Check if function exists
        exists = function_exists(function_name)

        if exists:
            print(f"Function exists - updating code...")
            if update_function(function_name, zip_content):
                success_count += 1
        else:
            print(f"Function does not exist - creating new...")
            description = descriptions.get(function_name, 'CFD Optimization Function')
            if create_function(function_name, zip_content, description):
                success_count += 1

    # Summary
    print("\n" + "=" * 60)
    print(f"Deployment Summary: {success_count}/{total_count} successful")
    print("=" * 60)

    if success_count == total_count:
        print("✓ All functions deployed successfully!")
        print("\nNext steps:")
        print("  1. Verify S3 bucket permissions")
        print("  2. Test Lambda functions with S3 storage")
        print("  3. Run integration tests")
    else:
        print(f"⚠ {total_count - success_count} function(s) failed")
        print("Check error messages above for details.")


if __name__ == '__main__':
    main()
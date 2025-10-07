# deploy_updated_lambdas.py
"""
Deploy CFD Optimization Lambda Functions

Handles both:
- UPDATE: Existing functions (tool functions)
- CREATE: New functions (orchestration functions)
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

# Lambda function mappings: folder_name -> AWS function name
LAMBDA_FUNCTIONS = {
    'generate_geometry': 'cfd-generate-geometry',
    'run_cfd': 'cfd-run-cfd',
    'get_next_candidates': 'cfd-get-next-candidates',
    'initialize_optimization': 'cfd-initialize-optimization',
    'check_convergence': 'cfd-check-convergence',
    'generate_report': 'cfd-generate-report'
}

lambda_client = boto3.client('lambda', region_name=REGION)


def create_deployment_package(function_folder):
    """
    Create a ZIP file containing the Lambda function code and dependencies.
    """
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

        # Add shared storage module if it exists
        storage_path = 'lambdas/shared/storage.py'
        if os.path.exists(storage_path):
            zip_file.write(storage_path, 'storage.py')
            print(f"  ✓ Added {storage_path}")

    zip_buffer.seek(0)
    return zip_buffer.read()


def function_exists(function_name):
    """
    Check if Lambda function already exists.
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
    """
    try:
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python3.12',
            Role=LAMBDA_ROLE_ARN,
            Handler='handler.lambda_handler',
            Code={'ZipFile': zip_content},
            Description=description,
            Timeout=30,
            MemorySize=256,
            Environment={
                'Variables': {
                    'LOG_LEVEL': 'INFO'
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
        'cfd-generate-report': 'Generate optimization summary report'
    }

    success_count = 0
    total_count = len(LAMBDA_FUNCTIONS)

    for folder_name, function_name in LAMBDA_FUNCTIONS.items():
        print(f"\n{folder_name} → {function_name}")
        print("-" * 60)

        # Create deployment package
        print("Creating deployment package...")
        zip_content = create_deployment_package(folder_name)

        if zip_content is None:
            print(f"  ✗ Skipping {function_name} (missing files)")
            continue

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
    else:
        print(f"⚠ {total_count - success_count} function(s) failed")
        print("Check error messages above for details.")


if __name__ == '__main__':
    main()
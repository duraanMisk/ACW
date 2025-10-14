#!/usr/bin/env python3
"""
Test Lambda Filesystem

Creates a test Lambda that lists all files in the deployment package.
"""

import boto3
import json
import time

lambda_client = boto3.client('lambda', region_name='us-east-1')
iam_client = boto3.client('iam', region_name='us-east-1')

TEST_FUNCTION_NAME = 'test-lambda-filesystem'
LAMBDA_ROLE_ARN = 'arn:aws:iam::120569639479:role/CFDOptimizationAgentStack-LambdaExecutionRoleC61CE2F-l2R78aFnANAv'


def create_test_handler():
    """Create a test handler that inspects the filesystem."""

    handler_code = '''
import json
import os
import sys

def lambda_handler(event, context):
    """List all files and test imports."""

    results = {
        'python_version': sys.version,
        'cwd': os.getcwd(),
        'files': {},
        'imports': {}
    }

    # List files in /var/task (Lambda deployment directory)
    task_dir = '/var/task'
    if os.path.exists(task_dir):
        results['files'][task_dir] = os.listdir(task_dir)

    # Check if our files exist
    for filename in ['session_manager.py', 'storage_s3.py', 'handler.py']:
        filepath = os.path.join(task_dir, filename)
        if os.path.exists(filepath):
            results['files'][filename] = {
                'exists': True,
                'size': os.path.getsize(filepath)
            }
        else:
            results['files'][filename] = {'exists': False}

    # Try importing
    try:
        import session_manager
        results['imports']['session_manager'] = {
            'success': True,
            'file': session_manager.__file__ if hasattr(session_manager, '__file__') else 'unknown'
        }
    except Exception as e:
        results['imports']['session_manager'] = {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }

    try:
        import storage_s3
        results['imports']['storage_s3'] = {
            'success': True,
            'file': storage_s3.__file__ if hasattr(storage_s3, '__file__') else 'unknown'
        }
    except Exception as e:
        results['imports']['storage_s3'] = {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }

    try:
        import boto3
        results['imports']['boto3'] = {
            'success': True,
            'version': boto3.__version__
        }
    except Exception as e:
        results['imports']['boto3'] = {
            'success': False,
            'error': str(e)
        }

    # Check sys.path
    results['sys_path'] = sys.path

    return {
        'statusCode': 200,
        'body': json.dumps(results, indent=2)
    }
'''

    return handler_code


def create_and_test_function():
    """Create a test Lambda function and invoke it."""

    print("=" * 60)
    print("Lambda Filesystem Test")
    print("=" * 60)

    print("\n1. Creating test handler code...")
    handler_code = create_test_handler()

    # Create a ZIP with the test handler
    import zipfile
    import io

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('handler.py', handler_code)

        # Add the shared files
        for filename in ['storage_s3.py', 'session_manager.py']:
            filepath = f'lambdas/shared/{filename}'
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    zip_file.writestr(filename, f.read())
                print(f"  ✓ Added {filename}")
            else:
                print(f"  ✗ {filename} not found")

    zip_buffer.seek(0)
    zip_content = zip_buffer.read()

    print(f"\n2. Created deployment package: {len(zip_content)} bytes")

    # Check if function exists
    try:
        lambda_client.get_function(FunctionName=TEST_FUNCTION_NAME)
        print(f"\n3. Deleting existing test function...")
        lambda_client.delete_function(FunctionName=TEST_FUNCTION_NAME)
        time.sleep(2)
    except lambda_client.exceptions.ResourceNotFoundException:
        pass

    print(f"\n4. Creating test Lambda function...")
    try:
        response = lambda_client.create_function(
            FunctionName=TEST_FUNCTION_NAME,
            Runtime='python3.12',
            Role=LAMBDA_ROLE_ARN,
            Handler='handler.lambda_handler',
            Code={'ZipFile': zip_content},
            Description='Test Lambda filesystem and imports',
            Timeout=30,
            MemorySize=256
        )
        print(f"  ✓ Function created")
    except Exception as e:
        print(f"  ✗ Failed to create function: {e}")
        return

    # Wait for function to be active
    print(f"\n5. Waiting for function to be ready...")
    time.sleep(3)

    # Invoke the function
    print(f"\n6. Invoking test function...")
    response = lambda_client.invoke(
        FunctionName=TEST_FUNCTION_NAME,
        Payload=json.dumps({})
    )

    result = json.loads(response['Payload'].read())

    if result['statusCode'] == 200:
        body = json.loads(result['body'])

        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        print(f"\nPython Version: {body['python_version'][:50]}...")
        print(f"Working Directory: {body['cwd']}")

        print(f"\nFiles in /var/task:")
        if '/var/task' in body['files']:
            for f in sorted(body['files']['/var/task']):
                print(f"  - {f}")

        print(f"\nShared Files:")
        for filename in ['session_manager.py', 'storage_s3.py']:
            if filename in body['files']:
                info = body['files'][filename]
                if info['exists']:
                    print(f"  ✓ {filename} ({info['size']} bytes)")
                else:
                    print(f"  ✗ {filename} NOT FOUND")

        print(f"\nImport Tests:")
        for module_name, info in body['imports'].items():
            if info['success']:
                extra = info.get('version', info.get('file', ''))
                print(f"  ✓ {module_name} - {extra}")
            else:
                print(f"  ✗ {module_name} - {info['error_type']}: {info['error']}")

        print(f"\nPython Path:")
        for path in body['sys_path'][:5]:
            print(f"  - {path}")

        # Cleanup
        print(f"\n7. Cleaning up test function...")
        lambda_client.delete_function(FunctionName=TEST_FUNCTION_NAME)
        print(f"  ✓ Test function deleted")

    else:
        print(f"\n✗ Test function returned error")
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    import os

    create_and_test_function()
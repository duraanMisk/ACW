#!/usr/bin/env python3
"""
Diagnose Lambda Import Issues

Invokes a Lambda to check what's actually in the deployment package.
"""

import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-east-1')


def test_lambda_imports():
    """Test what the Lambda can actually import."""

    print("=" * 60)
    print("Lambda Import Diagnostics")
    print("=" * 60)

    # Create a test event that will make the Lambda print diagnostic info
    payload = {
        'objective': 'minimize_cd',
        'cl_min': 0.30,
        'reynolds': 500000,
        'max_iter': 3
    }

    print("\nInvoking cfd-initialize-optimization...")

    response = lambda_client.invoke(
        FunctionName='cfd-initialize-optimization',
        Payload=json.dumps(payload),
        LogType='Tail'
    )

    result = json.loads(response['Payload'].read())

    print(f"\nResult:")
    print(f"  Status Code: {result['statusCode']}")
    print(f"  S3 Enabled: {result['body'].get('s3_enabled', 'unknown')}")

    # Get the function's environment variables
    print("\n" + "=" * 60)
    print("Environment Variables")
    print("=" * 60)

    config = lambda_client.get_function_configuration(
        FunctionName='cfd-initialize-optimization'
    )

    env_vars = config.get('Environment', {}).get('Variables', {})
    for key, value in env_vars.items():
        print(f"  {key}: {value}")

    # Download and inspect the deployment package
    print("\n" + "=" * 60)
    print("Deployment Package Contents")
    print("=" * 60)

    function_response = lambda_client.get_function(
        FunctionName='cfd-initialize-optimization'
    )

    code_url = function_response['Code']['Location']
    print(f"\nCode URL: {code_url[:80]}...")

    # Get the code size
    code_size = config.get('CodeSize', 0)
    print(f"Code Size: {code_size:,} bytes ({code_size / 1024:.1f} KB)")

    # We can't directly download and unzip from Python easily,
    # but we can check the logs more carefully
    print("\n" + "=" * 60)
    print("Checking CloudWatch Logs")
    print("=" * 60)

    logs_client = boto3.client('logs', region_name='us-east-1')

    # Get the latest log stream
    log_streams = logs_client.describe_log_streams(
        logGroupName='/aws/lambda/cfd-initialize-optimization',
        orderBy='LastEventTime',
        descending=True,
        limit=1
    )

    if log_streams['logStreams']:
        stream_name = log_streams['logStreams'][0]['logStreamName']

        # Get recent log events
        events = logs_client.get_log_events(
            logGroupName='/aws/lambda/cfd-initialize-optimization',
            logStreamName=stream_name,
            limit=20
        )

        print(f"\nRecent log messages:")
        for event in events['events']:
            message = event['message'].strip()
            if 'WARNING' in message or 'ERROR' in message or 'not available' in message:
                print(f"  {message}")


def create_import_test_lambda():
    """Create a simple test to check imports."""

    print("\n" + "=" * 60)
    print("Creating Import Test")
    print("=" * 60)

    # Create a minimal test handler
    test_code = """
import json
import sys
import os

def lambda_handler(event, context):
    results = {
        'python_version': sys.version,
        'python_path': sys.path,
        'cwd': os.getcwd(),
        'files_in_root': os.listdir('/var/task'),
    }

    # Try importing our modules
    try:
        import session_manager
        results['session_manager'] = 'SUCCESS'
        results['session_manager_location'] = session_manager.__file__
    except Exception as e:
        results['session_manager'] = f'FAILED: {str(e)}'

    try:
        import storage_s3
        results['storage_s3'] = 'SUCCESS'
        results['storage_s3_location'] = storage_s3.__file__
    except Exception as e:
        results['storage_s3'] = f'FAILED: {str(e)}'

    try:
        import boto3
        results['boto3'] = f'SUCCESS (version {boto3.__version__})'
    except Exception as e:
        results['boto3'] = f'FAILED: {str(e)}'

    return {
        'statusCode': 200,
        'body': results
    }
"""

    print("\nTest code created. To run this test:")
    print("1. Create a file: test_lambda_imports_handler.py")
    print("2. Copy the code above")
    print("3. Create a minimal Lambda function")
    print("4. Deploy with the same shared files")
    print("\nOr, let's check the actual deployment package...")


def main():
    test_lambda_imports()

    print("\n" + "=" * 60)
    print("DIAGNOSIS")
    print("=" * 60)
    print("\nThe Lambda shows 'S3 storage modules not available'")
    print("\nPossible causes:")
    print("  1. Import error in session_manager.py or storage_s3.py")
    print("  2. Files not at correct path in ZIP")
    print("  3. Python version mismatch")
    print("\nTo debug further:")
    print("  1. Check if files are in ZIP: unzip -l deployment.zip")
    print("  2. Try importing locally: python -c 'import session_manager'")
    print("  3. Check CloudWatch logs for actual error message")

    print("\n" + "=" * 60)
    print("IMMEDIATE FIX")
    print("=" * 60)
    print("\nLet me create a fixed version of the handlers that")
    print("shows the actual import error instead of hiding it...")


if __name__ == '__main__':
    main()
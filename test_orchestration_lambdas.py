# test_orchestration_lambdas.py
"""Quick test of the 3 new orchestration Lambda functions"""

import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-east-1')


def test_function(function_name, payload, description):
    print(f"\n{'=' * 60}")
    print(f"Testing: {description}")
    print(f"Function: {function_name}")
    print(f"{'=' * 60}")

    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            Payload=json.dumps(payload)
        )

        result = json.loads(response['Payload'].read())
        print("✓ Success!")
        print(json.dumps(result, indent=2))
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


# Test 1: Initialize Optimization
test_function(
    'cfd-initialize-optimization',
    {
        'objective': 'minimize_cd',
        'cl_min': 0.30,
        'reynolds': 500000,
        'max_iter': 5
    },
    'Initialize Optimization'
)

# Test 2: Check Convergence (will return "no results yet")
test_function(
    'cfd-check-convergence',
    {
        'max_iter': 8,
        'cl_min': 0.30
    },
    'Check Convergence'
)

# Test 3: Generate Report (will return "no data available")
test_function(
    'cfd-generate-report',
    {
        'reason': 'Test report',
        'cl_min': 0.30
    },
    'Generate Report'
)

print("\n" + "=" * 60)
print("✓ All tests complete!")
print("=" * 60)
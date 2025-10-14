# diagnose_stack.py
"""Diagnose CloudFormation stack issues - Windows compatible"""
import boto3
import json
from datetime import datetime


def diagnose_storage_stack():
    cfn = boto3.client('cloudformation', region_name='us-east-1')
    s3 = boto3.client('s3', region_name='us-east-1')

    stack_name = 'CFDOptimizationStorageStack'

    print("=" * 70)
    print("CFD OPTIMIZATION STORAGE STACK DIAGNOSTICS")
    print("=" * 70)

    # Check 1: Stack status
    print("\n1. STACK STATUS")
    print("-" * 70)
    try:
        response = cfn.describe_stacks(StackName=stack_name)
        stack = response['Stacks'][0]
        status = stack['StackStatus']
        print(f"Stack Status: {status}")

        if 'StackStatusReason' in stack:
            print(f"Reason: {stack['StackStatusReason']}")

    except cfn.exceptions.ClientError as e:
        if 'does not exist' in str(e):
            print("✓ Stack does not exist (good - we can create fresh)")
        else:
            print(f"Error checking stack: {e}")

    # Check 2: Recent errors
    print("\n2. RECENT ERRORS")
    print("-" * 70)
    try:
        events = cfn.describe_stack_events(StackName=stack_name)

        error_events = [
                           e for e in events['StackEvents']
                           if 'FAILED' in e['ResourceStatus']
                       ][:5]  # Last 5 errors

        if error_events:
            for event in error_events:
                print(f"\nTimestamp: {event['Timestamp']}")
                print(f"Resource: {event.get('LogicalResourceId', 'N/A')}")
                print(f"Status: {event['ResourceStatus']}")
                print(f"Reason: {event.get('ResourceStatusReason', 'N/A')}")
        else:
            print("No recent errors found")

    except Exception as e:
        print(f"Could not retrieve events: {e}")

    # Check 3: Bucket existence
    print("\n3. BUCKET CHECK")
    print("-" * 70)

    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']
    region = 'us-east-1'

    bucket_names = [
        f"cfd-optimization-data-{account_id}-{region}",
        f"cfd-opt-data-{region}-{account_id[:8]}",
        f"cfdoptimizationdatabucket",
    ]

    for bucket_name in bucket_names:
        try:
            s3.head_bucket(Bucket=bucket_name)
            print(f"✓ FOUND: {bucket_name}")

            # Check if empty
            response = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
            if 'Contents' in response:
                print(f"  ⚠ Bucket has {response['KeyCount']} objects")
            else:
                print(f"  ✓ Bucket is empty")

        except s3.exceptions.NoSuchBucket:
            print(f"✗ Not found: {bucket_name}")
        except Exception as e:
            print(f"✗ Error checking {bucket_name}: {e}")

    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)

    try:
        response = cfn.describe_stacks(StackName=stack_name)
        status = response['Stacks'][0]['StackStatus']

        if status == 'UPDATE_ROLLBACK_COMPLETE':
            print("\n⚠ Stack is in failed state (UPDATE_ROLLBACK_COMPLETE)")
            print("\nTO FIX:")
            print("1. Run: cdk destroy CFDOptimizationStorageStack")
            print("2. Wait for deletion")
            print("3. Run: cdk deploy CFDOptimizationStorageStack")

        elif status == 'ROLLBACK_COMPLETE':
            print("\n⚠ Stack creation failed (ROLLBACK_COMPLETE)")
            print("\nTO FIX:")
            print("1. Delete the stack first")
            print("2. Run: aws cloudformation delete-stack --stack-name CFDOptimizationStorageStack")
            print("3. Wait a minute, then: cdk deploy CFDOptimizationStorageStack")

    except:
        print("\n✓ No stack exists - ready for fresh deployment")
        print("\nTO DEPLOY:")
        print("1. Run: cdk deploy CFDOptimizationStorageStack")


if __name__ == "__main__":
    diagnose_storage_stack()
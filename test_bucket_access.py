# test_bucket_access.py
"""Test S3 bucket access from local machine"""
import boto3
import json


def test_bucket():
    s3 = boto3.client('s3', region_name='us-east-1')
    sts = boto3.client('sts')

    account_id = sts.get_caller_identity()['Account']
    bucket_name = f"cfd-optimization-data-{account_id}-us-east-1"

    print(f"Testing bucket: {bucket_name}")

    try:
        # Test 1: Bucket exists
        s3.head_bucket(Bucket=bucket_name)
        print("✓ Bucket exists")

        # Test 2: Can write
        test_key = 'test/hello.txt'
        s3.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=b'Hello from CDK deployment test'
        )
        print(f"✓ Can write: {test_key}")

        # Test 3: Can read
        obj = s3.get_object(Bucket=bucket_name, Key=test_key)
        content = obj['Body'].read().decode('utf-8')
        print(f"✓ Can read: {content}")

        # Test 4: Can delete
        s3.delete_object(Bucket=bucket_name, Key=test_key)
        print(f"✓ Can delete")

        print(f"\n✅ All tests passed! Bucket is ready.")

    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    test_bucket()
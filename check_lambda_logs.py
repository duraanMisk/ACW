#!/usr/bin/env python3
"""
Check CloudWatch logs for the run_cfd Lambda to see why S3 writes are failing.
"""

import boto3
import json
import time
from datetime import datetime, timedelta


def invoke_lambda_and_check_logs():
    """Invoke Lambda and immediately check logs."""
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    logs_client = boto3.client('logs', region_name='us-east-1')

    log_group = '/aws/lambda/cfd-run-cfd'

    print("=" * 60)
    print("Invoking cfd-run-cfd Lambda...")
    print("=" * 60)

    # Invoke Lambda
    session_id = f"debug-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    payload = {
        "apiPath": "/run_cfd",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "geometry_id", "value": "NACA4412_a2.0"},
                        {"name": "reynolds", "value": "500000"},
                        {"name": "alpha", "value": "2.0"}
                    ]
                }
            }
        },
        "SESSION_ID": session_id
    }

    print(f"Session ID: {session_id}")

    response = lambda_client.invoke(
        FunctionName='cfd-run-cfd',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )

    result = json.loads(response['Payload'].read())
    print(f"✅ Lambda completed")
    print(f"Response: {json.dumps(result, indent=2)}")

    # Wait a moment for logs to be available
    print("\n⏳ Waiting 3 seconds for logs...")
    time.sleep(3)

    # Get recent log streams
    print(f"\n📋 Fetching logs from {log_group}...")

    try:
        streams_response = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )

        if not streams_response['logStreams']:
            print("❌ No log streams found")
            return

        latest_stream = streams_response['logStreams'][0]
        stream_name = latest_stream['logStreamName']

        print(f"Latest log stream: {stream_name}")

        # Get log events
        events_response = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            startFromHead=False,
            limit=100
        )

        print("\n" + "=" * 60)
        print("LAMBDA LOGS (last 100 lines)")
        print("=" * 60)

        for event in events_response['events']:
            timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
            message = event['message'].strip()
            print(f"[{timestamp.strftime('%H:%M:%S')}] {message}")

        print("=" * 60)

        # Check for specific messages
        all_logs = '\n'.join([e['message'] for e in events_response['events']])

        if 'storage module not available' in all_logs.lower():
            print("\n❌ PROBLEM: Storage module failed to import!")
        elif 'wrote design to s3' in all_logs.lower():
            print("\n✅ SUCCESS: Lambda wrote to S3!")
        elif 'failed to write to s3' in all_logs.lower():
            print("\n⚠️  WARNING: S3 write attempted but failed")
        else:
            print("\n🤔 UNCLEAR: Check logs above for issues")

    except Exception as e:
        print(f"❌ Error fetching logs: {e}")


def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║           Debug: Check Lambda CloudWatch Logs             ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)

    invoke_lambda_and_check_logs()


if __name__ == "__main__":
    main()
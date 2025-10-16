# Create a quick continue script

import boto3
bedrock = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
response = bedrock.invoke_agent(
    agentId='MXUZMBTQFV',
    agentAliasId='MPGG39Y8EK',
    sessionId='agent-test-20251015-232236',  # Same session!
    inputText='Continue optimization - test all 5 candidates from get_next_candidates'
)
for event in response['completion']:
    if 'chunk' in event and 'bytes' in event['chunk']:
        print(event['chunk']['bytes'].decode(), end='', flush=True)

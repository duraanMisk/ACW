"""
Test Agent with Detailed Trace Output

This shows exactly where throttling or errors occur in the agent's execution.
"""

import boto3
import json
from datetime import datetime

# Configuration
AGENT_ID = 'MXUZMBTQFV'
ALIAS_ID = 'MPGG39Y8EK'
REGION = 'us-east-1'

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=REGION)


def test_agent_with_trace():
    """Test agent with full trace output."""

    session_id = f"trace-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print("=" * 70)
    print("BEDROCK AGENT TRACE TEST")
    print("=" * 70)
    print(f"Agent ID: {AGENT_ID}")
    print(f"Alias ID: {ALIAS_ID}")
    print(f"Session ID: {session_id}")
    print("=" * 70)
    print("\nSending simple request: 'Hello'\n")

    try:
        response = bedrock_agent_runtime.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=ALIAS_ID,
            sessionId=session_id,
            inputText="Hello",
            enableTrace=True  # Enable detailed trace
        )

        print("RESPONSE STREAM:")
        print("-" * 70)

        for event in response['completion']:
            print(f"\n[EVENT TYPE: {list(event.keys())}]")

            # Text chunks
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    text = chunk['bytes'].decode('utf-8')
                    print(f"TEXT: {text}")

            # Trace information
            elif 'trace' in event:
                trace = event['trace']
                print(f"\nTRACE: {json.dumps(trace, indent=2, default=str)}")

                # Check for specific trace types
                if 'trace' in trace:
                    inner_trace = trace['trace']

                    # Pre-processing
                    if 'preProcessingTrace' in inner_trace:
                        print("\n[PRE-PROCESSING]")
                        pre = inner_trace['preProcessingTrace']
                        print(json.dumps(pre, indent=2, default=str))

                    # Orchestration (tool calls)
                    if 'orchestrationTrace' in inner_trace:
                        print("\n[ORCHESTRATION]")
                        orch = inner_trace['orchestrationTrace']

                        # Model invocation
                        if 'modelInvocationInput' in orch:
                            print("  → Model invocation starting...")
                            inv = orch['modelInvocationInput']
                            print(f"     Text: {inv.get('text', 'N/A')[:100]}...")

                        # Rationale
                        if 'rationale' in orch:
                            print("  → Agent reasoning:")
                            print(f"     {orch['rationale'].get('text', 'N/A')}")

                        # Tool invocation
                        if 'invocationInput' in orch:
                            print("  → Invoking tool...")
                            tool = orch['invocationInput']
                            print(json.dumps(tool, indent=4, default=str))

                        # Observation (tool response)
                        if 'observation' in orch:
                            print("  → Tool response received")
                            obs = orch['observation']
                            print(json.dumps(obs, indent=4, default=str))

                    # Post-processing
                    if 'postProcessingTrace' in inner_trace:
                        print("\n[POST-PROCESSING]")
                        post = inner_trace['postProcessingTrace']
                        print(json.dumps(post, indent=2, default=str))

            # Return control
            elif 'returnControl' in event:
                print(f"\n[RETURN CONTROL]")
                print(json.dumps(event['returnControl'], indent=2, default=str))

            # Internal server exception
            elif 'internalServerException' in event:
                print(f"\n❌ INTERNAL SERVER ERROR")
                print(json.dumps(event['internalServerException'], indent=2, default=str))

            # Throttling exception
            elif 'throttlingException' in event:
                print(f"\n⚠ THROTTLING EXCEPTION")
                print(json.dumps(event['throttlingException'], indent=2, default=str))

            # Access denied
            elif 'accessDeniedException' in event:
                print(f"\n❌ ACCESS DENIED")
                print(json.dumps(event['accessDeniedException'], indent=2, default=str))

        print("\n" + "-" * 70)
        print("✓ Request completed successfully")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}")
        print(f"Message: {str(e)}")

        # Check if it's a throttling error
        if 'throttlingException' in str(e).lower():
            print("\n⚠ THROTTLING DETECTED")
            print("This means:")
            print("  1. Permissions are working ✓")
            print("  2. Too many recent requests")
            print("  3. Wait 10-30 minutes before retrying")

        # Check if it's access denied
        elif 'accessDenied' in str(e).lower():
            print("\n❌ ACCESS DENIED")
            print("Check:")
            print("  1. Agent role has bedrock:InvokeModel permission")
            print("  2. Agent role has bedrock:InvokeModelWithResponseStream permission")
            print("  3. Agent was re-prepared after permission changes")

        return False

    return True


if __name__ == '__main__':
    print(f"\nCurrent time: {datetime.now().strftime('%H:%M:%S')}\n")
    success = test_agent_with_trace()

    if success:
        print("\n🎉 Agent is working! Now you can run the full optimization test.")
    else:
        print("\n⚠ Check the trace output above for details.")
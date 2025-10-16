"""
Comprehensive Agent Diagnostics

This script checks:
1. Is the v3 prompt actually loaded in the agent?
2. What does the agent's reasoning trace show?
3. Are iteration parameters being passed to Lambdas?
4. What tool responses did the agent actually receive?
5. When does the hallucination happen?
"""

import boto3
import json
from datetime import datetime, timedelta

# Configuration
AGENT_ID = 'MXUZMBTQFV'
ALIAS_ID = 'MPGG39Y8EK'
REGION = 'us-east-1'
BUCKET_NAME = 'cfd-optimization-data-120569639479-us-east-1'

# Last test session (update this with your latest session ID)
LAST_SESSION_ID = 'agent-test-20251015-012005'

# Initialize clients
bedrock_agent = boto3.client('bedrock-agent', region_name=REGION)
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=REGION)
s3_client = boto3.client('s3', region_name=REGION)
logs_client = boto3.client('logs', region_name=REGION)


def check_agent_prompt():
    """Diagnostic 1: Check if v3 prompt is actually loaded."""
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 1: Agent Prompt Check")
    print("=" * 70)

    try:
        response = bedrock_agent.get_agent(agentId=AGENT_ID)
        agent = response['agent']

        instruction = agent.get('instruction', '')

        print(f"Agent Status: {agent['agentStatus']}")
        print(f"Updated At: {agent.get('updatedAt')}")
        print(f"Instruction Length: {len(instruction)} characters")

        # Check for v3 indicators
        v3_indicators = {
            'Rule #1: NEVER MAKE UP DATA': 'Rule #1 present',
            'Rule #2: VALIDATE CONSTRAINTS': 'Rule #2 present',
            'Rule #3: MANDATORY OPTIMIZATION': 'Rule #3 present',
            'NEVER MAKE UP DATA': 'Anti-hallucination section',
            'get_next_candidates': 'Mentions get_next_candidates',
            'CONSTRAINT VALIDATION': 'Constraint validation section',
            'FORBIDDEN BEHAVIORS': 'Forbidden behaviors section'
        }

        print(f"\n✓ V3 Prompt Indicators:")
        found_count = 0
        for indicator, description in v3_indicators.items():
            if indicator in instruction:
                print(f"  ✓ {description}")
                found_count += 1
            else:
                print(f"  ✗ {description} - MISSING")

        print(f"\nFound {found_count}/{len(v3_indicators)} v3 indicators")

        if found_count >= 5:
            print("✓ V3 prompt appears to be loaded correctly")
            return True
        else:
            print("⚠ V3 prompt may not be fully loaded")

            # Show a sample of what IS there
            print(f"\nFirst 500 chars of actual prompt:")
            print("-" * 70)
            print(instruction[:500])
            print("-" * 70)
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def analyze_agent_trace():
    """Diagnostic 2: Get detailed agent reasoning trace."""
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 2: Agent Reasoning Trace")
    print("=" * 70)

    print(f"Re-invoking agent with trace enabled to see reasoning...")

    try:
        # Make a simple request to see the trace
        response = bedrock_agent_runtime.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=ALIAS_ID,
            sessionId=f'diagnostic-{datetime.now().strftime("%H%M%S")}',
            inputText='Generate NACA 4412 at 2 degrees and run CFD',
            enableTrace=True
        )

        print("\n📋 Trace Events:")
        print("-" * 70)

        tool_calls = []
        observations = []
        reasoning = []

        for event in response['completion']:
            if 'trace' in event:
                trace = event['trace']

                if 'trace' in trace:
                    inner = trace['trace']

                    # Orchestration trace
                    if 'orchestrationTrace' in inner:
                        orch = inner['orchestrationTrace']

                        # Rationale (agent's reasoning)
                        if 'rationale' in orch:
                            rationale_text = orch['rationale'].get('text', '')
                            reasoning.append(rationale_text)
                            print(f"\n💭 AGENT REASONING:")
                            print(f"   {rationale_text[:200]}...")

                        # Tool invocation
                        if 'invocationInput' in orch:
                            inv = orch['invocationInput']
                            if 'actionGroupInvocationInput' in inv:
                                action = inv['actionGroupInvocationInput']
                                tool_name = action.get('apiPath', 'unknown')
                                tool_calls.append(tool_name)
                                print(f"\n🔧 TOOL CALL: {tool_name}")

                        # Observation (tool response)
                        if 'observation' in orch:
                            obs = orch['observation']
                            if 'actionGroupInvocationOutput' in obs:
                                output = obs['actionGroupInvocationOutput']
                                text = output.get('text', '')
                                observations.append(text)
                                print(f"\n📥 TOOL RESPONSE:")
                                print(f"   {text[:200]}...")

            elif 'chunk' in event:
                # This is the final response to user
                pass

        print("\n" + "-" * 70)
        print(f"\nSummary:")
        print(f"  Tool calls: {len(tool_calls)} - {tool_calls}")
        print(f"  Observations: {len(observations)}")
        print(f"  Reasoning steps: {len(reasoning)}")

        # Check if agent mentions get_next_candidates in reasoning
        mentions_gnc = any('get_next_candidates' in r.lower() for r in reasoning)
        print(f"\n  Agent mentioned get_next_candidates: {mentions_gnc}")

        return {
            'tool_calls': tool_calls,
            'observations': observations,
            'reasoning': reasoning,
            'mentions_get_next_candidates': mentions_gnc
        }

    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def check_lambda_logs():
    """Diagnostic 3: Check CloudWatch logs for iteration parameters."""
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 3: Lambda CloudWatch Logs")
    print("=" * 70)

    lambda_functions = [
        'cfd-generate-geometry',
        'cfd-run-cfd',
        'cfd-get-next-candidates'
    ]

    # Look at logs from last 10 minutes
    start_time = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)

    for func_name in lambda_functions:
        log_group = f'/aws/lambda/{func_name}'

        print(f"\n📝 {func_name}:")
        print("-" * 70)

        try:
            # Get recent log streams
            streams_response = logs_client.describe_log_streams(
                logGroupName=log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=3
            )

            if not streams_response.get('logStreams'):
                print("  ⚠ No recent log streams")
                continue

            # Get events from most recent stream
            stream_name = streams_response['logStreams'][0]['logStreamName']

            events_response = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                startTime=start_time,
                limit=50
            )

            events = events_response.get('events', [])

            if not events:
                print("  ⚠ No recent events")
                continue

            print(f"  Found {len(events)} log events")

            # Look for key information
            for event in events:
                message = event['message']

                # Check for iteration parameter
                if 'iteration' in message.lower():
                    print(f"  ✓ Found iteration param: {message[:100]}...")

                # Check for extracted parameters
                if 'Extracted parameters' in message:
                    print(f"  📦 Parameters: {message}")

                # Check for S3 saves
                if 'Saved iteration summary' in message or 'iteration_' in message:
                    print(f"  💾 S3 write: {message[:100]}...")

            # Specific check for run_cfd iteration parameter
            if func_name == 'cfd-run-cfd':
                has_iteration = any('iteration' in e['message'].lower() for e in events)
                print(f"\n  ⚠ run_cfd receiving iteration parameter: {has_iteration}")

                if not has_iteration:
                    print("  → This explains why no iteration files are being created!")

        except logs_client.exceptions.ResourceNotFoundException:
            print(f"  ✗ Log group not found (function may not have been called)")
        except Exception as e:
            print(f"  ✗ Error: {e}")


def check_s3_data():
    """Diagnostic 4: Analyze S3 data from last test."""
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 4: S3 Data Analysis")
    print("=" * 70)

    prefix = f"sessions/{LAST_SESSION_ID}/"

    try:
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix=prefix
        )

        if 'Contents' not in response:
            print(f"✗ No S3 data found for session {LAST_SESSION_ID}")
            return

        files = [obj['Key'] for obj in response['Contents']]

        print(f"Session: {LAST_SESSION_ID}")
        print(f"Files found: {len(files)}\n")

        # Check each design file
        design_files = [f for f in files if '/designs/' in f and f.endswith('.json')]

        print(f"📁 Design Files ({len(design_files)}):")
        for design_file in design_files:
            obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=design_file)
            data = json.loads(obj['Body'].read())

            print(f"\n  File: {design_file.split('/')[-1]}")
            print(f"    geometry_id: {data.get('geometry_id')}")
            print(f"    Cl: {data.get('Cl')}")
            print(f"    Cd: {data.get('Cd')}")
            print(f"    timestamp: {data.get('timestamp')}")

        # Check iteration files
        iteration_files = [f for f in files if '/iterations/' in f]

        print(f"\n📁 Iteration Files ({len(iteration_files)}):")
        if iteration_files:
            for iter_file in iteration_files:
                obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=iter_file)
                data = json.loads(obj['Body'].read())
                print(f"  Iteration {data.get('iteration')}: {data.get('geometry_id')}")
        else:
            print("  ⚠ No iteration files found")
            print("  → This confirms iteration parameter is not being passed/saved")

    except Exception as e:
        print(f"✗ Error: {e}")


def compare_tool_output_vs_agent_claim():
    """Diagnostic 5: Compare what tools returned vs what agent said."""
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 5: Tool Output vs Agent Claims")
    print("=" * 70)

    # This requires running the test again with full trace capture
    print("This diagnostic requires a fresh test run with trace enabled.")
    print("The test_agent_optimization_v2.py already does this comparison.")
    print("\nKey finding from last run:")
    print("  Tool returned: Cd=0.02006")
    print("  Agent claimed: Cd=0.01483")
    print("  Difference: 0.00523 (26% error!)")


def main():
    """Run all diagnostics."""
    print("\n" + "=" * 70)
    print(" AGENT BEHAVIOR DIAGNOSTICS")
    print("=" * 70)
    print(f"Agent ID: {AGENT_ID}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    results = {}

    # Run diagnostics
    results['prompt_loaded'] = check_agent_prompt()
    results['trace_data'] = analyze_agent_trace()
    check_lambda_logs()
    check_s3_data()
    compare_tool_output_vs_agent_claim()

    # Summary
    print("\n" + "=" * 70)
    print(" DIAGNOSTIC SUMMARY")
    print("=" * 70)

    print(f"\n1. V3 Prompt Loaded: {results['prompt_loaded']}")

    if results['trace_data']:
        print(f"2. Tool Calls in Test: {len(results['trace_data']['tool_calls'])}")
        print(f"   - Calls: {results['trace_data']['tool_calls']}")
        print(f"3. Agent Mentions get_next_candidates: {results['trace_data']['mentions_get_next_candidates']}")

    print(f"\n🔍 Key Findings:")
    print(f"  - Iteration parameter being passed: Check logs above")
    print(f"  - Agent following v3 prompt: Check trace reasoning above")
    print(f"  - Hallucination occurring: YES (confirmed in last test)")

    print(f"\n💡 Recommended Next Steps:")
    print(f"  1. If v3 prompt NOT loaded → Re-run update script")
    print(f"  2. If iteration param NOT passed → Fix test to pass iteration")
    print(f"  3. If agent reasoning looks wrong → Try simpler/shorter prompt")
    print(f"  4. If agent never mentions get_next_candidates → Prompt not working")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
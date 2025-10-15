"""
End-to-End Agent Optimization Test

This test validates the complete agent orchestration workflow:
1. Agent receives optimization request
2. Agent autonomously calls tools (generate_geometry, run_cfd, get_next_candidates)
3. Agent iterates through multiple design evaluations
4. Agent detects convergence or max iterations
5. Results are stored in S3
6. Final report is generated

This proves the Bedrock Agent can orchestrate the full optimization loop.
"""

import boto3
import json
import time
from datetime import datetime
import sys

# AWS Configuration
REGION = 'us-east-1'
BUCKET_NAME = 'cfd-optimization-data-120569639479-us-east-1'

# Agent configuration (load from agent_config.json if available)
try:
    with open('agent/agent_config.json', 'r') as f:
        config = json.load(f)
        AGENT_ID = config.get('agent_id')
        ALIAS_ID = config.get('alias_id')
except:
    # Fallback to manual entry
    AGENT_ID = 'MXUZMBTQFV'
    ALIAS_ID = 'TSTALIASID'  # or 'MPGG39Y8EK' for production

# Initialize clients with longer timeout
from botocore.config import Config

config = Config(
    read_timeout=300,  # 5 minutes
    connect_timeout=60,
    retries={'max_attempts': 0}  # No auto-retries to avoid confusion
)

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=REGION, config=config)
s3_client = boto3.client('s3', region_name=REGION)


def invoke_agent(session_id, prompt):
    """
    Invoke Bedrock Agent and stream the response.

    Args:
        session_id: Unique session identifier
        prompt: User instruction to the agent

    Returns:
        tuple: (full_response_text, tool_calls_made)
    """
    print(f"\n{'=' * 70}")
    print(f"Invoking Agent")
    print(f"{'=' * 70}")
    print(f"Session ID: {session_id}")
    print(f"Prompt: {prompt}")
    print(f"{'=' * 70}\n")

    try:
        response = bedrock_agent_runtime.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=ALIAS_ID,
            sessionId=session_id,
            inputText=prompt
        )

        full_response = ""
        tool_calls = []
        chunk_count = 0

        print("Agent Response (streaming):")
        print("-" * 70)

        for event in response['completion']:
            chunk_count += 1

            # Handle different event types
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    text = chunk['bytes'].decode('utf-8')
                    full_response += text
                    print(text, end='', flush=True)

            # Track tool invocations
            elif 'trace' in event:
                trace = event['trace'].get('trace', {})

                # Orchestration trace (tool calls)
                if 'orchestrationTrace' in trace:
                    orch = trace['orchestrationTrace']

                    # Tool invocation
                    if 'invocationInput' in orch:
                        invocation = orch['invocationInput']
                        if 'actionGroupInvocationInput' in invocation:
                            action = invocation['actionGroupInvocationInput']
                            tool_name = action.get('apiPath', 'unknown')
                            tool_calls.append({
                                'tool': tool_name,
                                'timestamp': datetime.now().isoformat()
                            })
                            print(f"\n[TOOL CALL: {tool_name}]", flush=True)

                    # Observation (tool response)
                    if 'observation' in orch:
                        obs = orch['observation']
                        if 'actionGroupInvocationOutput' in obs:
                            output = obs['actionGroupInvocationOutput']
                            print(f"[TOOL RESPONSE RECEIVED]", flush=True)

        print("\n" + "-" * 70)
        print(f"✓ Agent response complete ({chunk_count} chunks, {len(tool_calls)} tool calls)")

        return full_response, tool_calls

    except Exception as e:
        print(f"\n✗ Error invoking agent: {str(e)}")
        if 'ThrottlingException' in str(e):
            print("\n⚠ Rate limit hit. Wait 5-10 minutes and try again.")
        return None, []


def verify_s3_results(session_id):
    """
    Verify that the agent's actions resulted in proper S3 storage.

    Args:
        session_id: Session ID to check

    Returns:
        dict: Summary of S3 contents
    """
    print(f"\n{'=' * 70}")
    print(f"Verifying S3 Results")
    print(f"{'=' * 70}")

    summary = {
        'session_exists': False,
        'designs_count': 0,
        'iterations_count': 0,
        'has_design_history': False,
        'designs': [],
        'iterations': []
    }

    prefix = f"sessions/{session_id}/"

    try:
        # Check session file
        try:
            s3_client.head_object(Bucket=BUCKET_NAME, Key=f"{prefix}session.json")
            summary['session_exists'] = True
            print(f"✓ Session file exists")
        except:
            print(f"✗ Session file not found")

        # Check design_history.csv
        try:
            response = s3_client.get_object(Bucket=BUCKET_NAME, Key=f"{prefix}design_history.csv")
            csv_content = response['Body'].read().decode('utf-8')
            lines = csv_content.strip().split('\n')
            summary['has_design_history'] = True
            summary['designs_count'] = len(lines) - 1  # Subtract header
            print(f"✓ Design history: {summary['designs_count']} designs")

            # Parse designs
            if len(lines) > 1:
                header = lines[0].split(',')
                for line in lines[1:]:
                    values = line.split(',')
                    design = dict(zip(header, values))
                    summary['designs'].append(design)
        except:
            print(f"✗ Design history not found")

        # Count design files
        try:
            response = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME,
                Prefix=f"{prefix}designs/"
            )
            if 'Contents' in response:
                design_files = [obj['Key'] for obj in response['Contents'] if not obj['Key'].endswith('/')]
                print(f"✓ Design files: {len(design_files)}")
        except:
            pass

        # Count iteration files
        try:
            response = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME,
                Prefix=f"{prefix}iterations/"
            )
            if 'Contents' in response:
                iteration_files = [obj['Key'] for obj in response['Contents'] if not obj['Key'].endswith('/')]
                summary['iterations_count'] = len(iteration_files)
                summary['iterations'] = iteration_files
                print(f"✓ Iteration files: {len(iteration_files)}")

                # Show iteration details
                for iter_file in iteration_files:
                    iter_obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=iter_file)
                    iter_data = json.loads(iter_obj['Body'].read())
                    print(
                        f"  - Iteration {iter_data['iteration']}: {iter_data['geometry_id']} (Cd={iter_data['results']['Cd']:.5f})")
        except Exception as e:
            print(f"⚠ Could not read iteration files: {e}")

    except Exception as e:
        print(f"✗ Error checking S3: {str(e)}")

    return summary


def analyze_optimization_results(summary):
    """
    Analyze the optimization results and provide insights.

    Args:
        summary: S3 summary dict

    Returns:
        dict: Analysis results
    """
    print(f"\n{'=' * 70}")
    print(f"Optimization Analysis")
    print(f"{'=' * 70}")

    if not summary['designs']:
        print("✗ No designs found to analyze")
        return None

    # Find best design
    best_design = min(summary['designs'], key=lambda d: float(d['Cd']))

    # Calculate statistics
    cds = [float(d['Cd']) for d in summary['designs']]
    cls = [float(d['Cl']) for d in summary['designs']]

    analysis = {
        'total_evaluations': len(summary['designs']),
        'best_design': best_design,
        'best_cd': float(best_design['Cd']),
        'best_cl': float(best_design['Cl']),
        'cd_range': (min(cds), max(cds)),
        'cl_range': (min(cls), max(cls)),
        'improvement': ((max(cds) - min(cds)) / max(cds) * 100) if len(cds) > 1 else 0
    }

    print(f"\nTotal Evaluations: {analysis['total_evaluations']}")
    print(f"\nBest Design:")
    print(f"  Geometry: {best_design['geometry_id']}")
    print(f"  Cd: {analysis['best_cd']:.5f}")
    print(f"  Cl: {analysis['best_cl']:.4f}")
    print(f"  L/D: {float(best_design['L_D']):.2f}")

    if len(summary['designs']) > 1:
        print(f"\nOptimization Progress:")
        print(f"  Cd improved by: {analysis['improvement']:.1f}%")
        print(f"  Cd range: {analysis['cd_range'][0]:.5f} → {analysis['cd_range'][1]:.5f}")

    # Check constraint satisfaction
    constraint_satisfied = all(float(d['Cl']) >= 0.30 for d in summary['designs'])
    print(f"\nConstraint Check (Cl ≥ 0.30):")
    if constraint_satisfied:
        print(f"  ✓ All designs satisfy constraint")
    else:
        failing = [d for d in summary['designs'] if float(d['Cl']) < 0.30]
        print(f"  ✗ {len(failing)} design(s) violate constraint")

    return analysis


def run_agent_optimization_test():
    """
    Run complete end-to-end agent optimization test.
    """
    print("\n" + "=" * 70)
    print(" BEDROCK AGENT - END-TO-END OPTIMIZATION TEST")
    print("=" * 70)
    print(f"Agent ID: {AGENT_ID}")
    print(f"Alias ID: {ALIAS_ID}")
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    # Generate unique session ID
    session_id = f"agent-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Optimization prompt
    prompt = """
Please optimize an airfoil design to minimize drag coefficient (Cd) while maintaining lift coefficient (Cl) ≥ 0.30.

Requirements:
- Run 3 optimization iterations
- Start with NACA 4412 airfoil at 2° angle of attack
- Use Reynolds number 500,000
- Track iteration number for each CFD run
- Report the best design found

Please begin the optimization.
"""

    # Invoke agent
    print("\n🚀 Starting agent optimization...")
    start_time = time.time()

    response_text, tool_calls = invoke_agent(session_id, prompt)

    elapsed_time = time.time() - start_time

    if response_text is None:
        print("\n✗ Agent invocation failed")
        return False

    # Summary of agent actions
    print(f"\n{'=' * 70}")
    print(f"Agent Execution Summary")
    print(f"{'=' * 70}")
    print(f"Execution time: {elapsed_time:.1f} seconds")
    print(f"Tool calls made: {len(tool_calls)}")

    if tool_calls:
        print(f"\nTool Call Sequence:")
        for i, call in enumerate(tool_calls, 1):
            print(f"  {i}. {call['tool']} at {call['timestamp']}")

    # Wait a moment for S3 writes to complete
    print("\n⏳ Waiting for S3 writes to complete...")
    time.sleep(2)

    # Verify S3 results
    summary = verify_s3_results(session_id)

    # Analyze results
    analysis = analyze_optimization_results(summary)

    # Final verdict
    print(f"\n{'=' * 70}")
    print(f"TEST VERDICT")
    print(f"{'=' * 70}")

    success_criteria = [
        ("Agent responded", response_text is not None),
        ("Tool calls made", len(tool_calls) >= 3),
        ("Session created", summary['session_exists']),
        ("Designs evaluated", summary['designs_count'] >= 1),
        ("Iterations tracked", summary['iterations_count'] >= 1),
        ("Constraint satisfied", analysis is not None and all(float(d['Cl']) >= 0.30 for d in summary['designs']))
    ]

    passed = sum(1 for _, result in success_criteria if result)
    total = len(success_criteria)

    for criterion, result in success_criteria:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status:8} {criterion}")

    print(f"\n{'=' * 70}")
    print(f"Result: {passed}/{total} criteria passed")
    print(f"{'=' * 70}")

    if passed == total:
        print("\n🎉 SUCCESS! Agent optimization completed successfully!")
        print(f"\nView results:")
        print(f"  S3: s3://{BUCKET_NAME}/sessions/{session_id}/")
        print(f"\nNext steps:")
        print(f"  1. Review agent reasoning in response")
        print(f"  2. Test with longer optimization runs (5-8 iterations)")
        print(f"  3. Integrate with Step Functions for autonomous loops")
        return True
    else:
        print(f"\n⚠ TEST INCOMPLETE: {total - passed} criteria not met")
        print(f"\nDebugging:")
        print(f"  - Check agent logs: aws logs tail /aws/lambda/cfd-* --follow")
        print(f"  - Verify agent has access to all three tools")
        print(f"  - Check if rate limits were hit")
        return False


if __name__ == '__main__':
    success = run_agent_optimization_test()
    sys.exit(0 if success else 1)
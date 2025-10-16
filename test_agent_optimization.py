"""
End-to-End Agent Optimization Test v2

Improvements over v1:
- Uses S3 as source of truth instead of trace parsing
- Better error handling and retry logic
- Clearer success criteria
- Actual vs. reported data comparison
"""

import boto3
import json
import time
from datetime import datetime
import sys
from botocore.config import Config

# AWS Configuration
REGION = 'us-east-1'
BUCKET_NAME = 'cfd-optimization-data-120569639479-us-east-1'

# Agent configuration
try:
    with open('agent/agent_config.json', 'r') as f:
        config = json.load(f)
        AGENT_ID = config.get('agent_id')
        ALIAS_ID = config.get('alias_id')
except:
    AGENT_ID = 'MXUZMBTQFV'
    ALIAS_ID = 'MPGG39Y8EK'

# Initialize clients with longer timeout
boto_config = Config(
    read_timeout=300,  # 5 minutes
    connect_timeout=60,
    retries={'max_attempts': 0}
)

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=REGION, config=boto_config)
s3_client = boto3.client('s3', region_name=REGION)


def invoke_agent(session_id, prompt):
    """
    Invoke Bedrock Agent and capture response.

    Returns:
        tuple: (full_response_text, success_boolean)
    """
    print(f"\n{'=' * 70}")
    print(f"Invoking Agent")
    print(f"{'=' * 70}")
    print(f"Session ID: {session_id}")
    print(f"Prompt: {prompt[:100]}...")
    print(f"{'=' * 70}\n")

    try:
        response = bedrock_agent_runtime.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=ALIAS_ID,
            sessionId=session_id,
            inputText=prompt
        )

        full_response = ""

        print("Agent Response (streaming):")
        print("-" * 70)

        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    text = chunk['bytes'].decode('utf-8')
                    full_response += text
                    print(text, end='', flush=True)

        print("\n" + "-" * 70)
        print(f"✓ Agent response complete")

        return full_response, True

    except Exception as e:
        error_msg = str(e)
        print(f"\n✗ Error invoking agent: {error_msg}")

        if 'throttlingException' in error_msg.lower():
            print("\n⚠ THROTTLING: Wait 10-15 minutes before retrying")
        elif 'timeout' in error_msg.lower():
            print("\n⚠ TIMEOUT: Agent took too long (>5 minutes)")

        return None, False


def wait_for_s3_consistency(session_id, max_wait=30):
    """
    Wait for S3 to have files (eventual consistency).

    Returns:
        bool: True if files found, False if timeout
    """
    print(f"\n⏳ Waiting for S3 files to appear (eventual consistency)...")

    prefix = f"sessions/{session_id}/"

    for i in range(max_wait):
        try:
            response = s3_client.list_objects_v2(
                Bucket=BUCKET_NAME,
                Prefix=prefix
            )

            if 'Contents' in response:
                file_count = len([obj for obj in response['Contents'] if not obj['Key'].endswith('/')])
                if file_count > 0:
                    print(f"✓ Found {file_count} files in S3")
                    return True
        except:
            pass

        if i < max_wait - 1:
            time.sleep(1)

    print(f"⚠ No files found after {max_wait} seconds")
    return False


def analyze_s3_results(session_id):
    """
    Analyze S3 data to determine what actually happened.

    Returns:
        dict: Analysis summary
    """
    print(f"\n{'=' * 70}")
    print(f"Analyzing S3 Results")
    print(f"{'=' * 70}")

    summary = {
        'session_exists': False,
        'designs_evaluated': 0,
        'iterations_tracked': 0,
        'designs': [],
        'iterations': [],
        'best_design': None,
        'constraint_satisfied': False,
        'tool_calls_detected': 0
    }

    prefix = f"sessions/{session_id}/"

    try:
        # List all files
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix=prefix,
            MaxKeys=100
        )

        if 'Contents' not in response:
            print("✗ No S3 data found")
            return summary

        files = [obj['Key'] for obj in response['Contents']]
        print(f"✓ Found {len(files)} S3 objects")

        # Check session file
        session_file = f"{prefix}session.json"
        if session_file in files:
            summary['session_exists'] = True
            print(f"✓ Session file exists")

        # Count design files
        design_files = [f for f in files if '/designs/' in f and f.endswith('.json')]
        summary['designs_evaluated'] = len(design_files)
        summary['tool_calls_detected'] = len(design_files)  # Each design = 2 tool calls (generate + cfd)
        print(f"✓ Design files: {len(design_files)}")

        # Count iteration files
        iteration_files = [f for f in files if '/iterations/' in f and f.endswith('.json')]
        summary['iterations_tracked'] = len(iteration_files)
        print(f"✓ Iteration files: {len(iteration_files)}")

        # Read design_history.csv if exists
        csv_file = f"{prefix}design_history.csv"
        if csv_file in files:
            try:
                obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=csv_file)
                csv_content = obj['Body'].read().decode('utf-8')
                lines = csv_content.strip().split('\n')[1:]  # Skip header

                if lines:
                    print(f"\n📊 Design History ({len(lines)} designs):")
                    print(f"{'Geometry ID':<20} {'Cl':>8} {'Cd':>8} {'L/D':>8} {'Constraint':<12}")
                    print("-" * 70)

                    for line in lines:
                        parts = line.split(',')
                        if len(parts) >= 8:
                            geometry_id = parts[1]
                            cl = float(parts[2])
                            cd = float(parts[3])
                            ld = float(parts[4])

                            constraint_ok = cl >= 0.30
                            constraint_str = "✓ SATISFIED" if constraint_ok else "✗ VIOLATED"

                            design_data = {
                                'geometry_id': geometry_id,
                                'Cl': cl,
                                'Cd': cd,
                                'L_D': ld,
                                'constraint_satisfied': constraint_ok
                            }
                            summary['designs'].append(design_data)

                            print(f"{geometry_id:<20} {cl:>8.4f} {cd:>8.5f} {ld:>8.2f} {constraint_str:<12}")

                    # Find best design (lowest Cd with Cl >= 0.30)
                    feasible_designs = [d for d in summary['designs'] if d['constraint_satisfied']]

                    if feasible_designs:
                        summary['best_design'] = min(feasible_designs, key=lambda d: d['Cd'])
                        summary['constraint_satisfied'] = True
                        print(f"\n✓ Best feasible design: {summary['best_design']['geometry_id']}")
                        print(f"  Cd: {summary['best_design']['Cd']:.5f}")
                        print(f"  Cl: {summary['best_design']['Cl']:.4f}")
                    else:
                        print(f"\n✗ No designs satisfy Cl ≥ 0.30 constraint")
                        # Find design with lowest Cd anyway (even if infeasible)
                        if summary['designs']:
                            summary['best_design'] = min(summary['designs'], key=lambda d: d['Cd'])
                            print(f"  Lowest Cd (infeasible): {summary['best_design']['geometry_id']}")
                            print(f"    Cd: {summary['best_design']['Cd']:.5f}")
                            print(f"    Cl: {summary['best_design']['Cl']:.4f} (< 0.30)")

            except Exception as e:
                print(f"⚠ Could not parse design_history.csv: {e}")

    except Exception as e:
        print(f"✗ Error analyzing S3: {str(e)}")

    return summary


def extract_agent_claims(response_text):
    """
    Parse agent's response to extract what it CLAIMS as results.

    Returns:
        dict: Claimed results
    """
    claims = {
        'final_geometry': None,
        'final_cd': None,
        'final_cl': None,
        'mentions_get_next_candidates': False
    }

    # Look for common patterns in agent responses
    if response_text:
        # Check if agent mentioned get_next_candidates
        if 'get_next_candidates' in response_text.lower() or 'candidates' in response_text.lower():
            claims['mentions_get_next_candidates'] = True

        # Try to extract geometry ID claims
        import re
        geometry_pattern = r'NACA\d{4}_a[\d.]+|NACA\d{4}'
        geometries = re.findall(geometry_pattern, response_text)
        if geometries:
            claims['final_geometry'] = geometries[-1]  # Last mentioned

        # Try to extract Cd values
        cd_pattern = r'Cd\s*[=:]\s*([\d.]+)'
        cds = re.findall(cd_pattern, response_text)
        if cds:
            try:
                claims['final_cd'] = float(cds[-1])
            except:
                pass

        # Try to extract Cl values
        cl_pattern = r'Cl\s*[=:]\s*([\d.]+)'
        cls = re.findall(cl_pattern, response_text)
        if cls:
            try:
                claims['final_cl'] = float(cls[-1])
            except:
                pass

    return claims


def compare_claims_vs_reality(claims, s3_summary):
    """
    Compare what agent claimed vs. what actually happened in S3.

    Returns:
        dict: Comparison results
    """
    print(f"\n{'=' * 70}")
    print(f"Agent Claims vs. Reality")
    print(f"{'=' * 70}")

    comparison = {
        'geometry_match': False,
        'data_hallucinated': False,
        'constraint_validated': False
    }

    # Check geometry
    if claims['final_geometry'] and s3_summary['best_design']:
        actual_geometry = s3_summary['best_design']['geometry_id']
        claimed_geometry = claims['final_geometry']

        print(f"\nGeometry ID:")
        print(f"  Agent claimed: {claimed_geometry}")
        print(f"  S3 shows:      {actual_geometry}")

        if claimed_geometry == actual_geometry:
            print(f"  ✓ MATCH - Agent reported correctly")
            comparison['geometry_match'] = True
        else:
            print(f"  ✗ MISMATCH - Agent hallucinated geometry ID")
            comparison['data_hallucinated'] = True

    # Check Cd value
    if claims['final_cd'] is not None and s3_summary['best_design']:
        actual_cd = s3_summary['best_design']['Cd']
        claimed_cd = claims['final_cd']

        print(f"\nDrag Coefficient (Cd):")
        print(f"  Agent claimed: {claimed_cd:.5f}")
        print(f"  S3 shows:      {actual_cd:.5f}")

        diff = abs(claimed_cd - actual_cd)
        if diff < 0.0001:
            print(f"  ✓ MATCH - Agent reported correctly")
        else:
            print(f"  ✗ MISMATCH (diff: {diff:.5f}) - Agent hallucinated value")
            comparison['data_hallucinated'] = True

    # Check Cl value
    if claims['final_cl'] is not None and s3_summary['best_design']:
        actual_cl = s3_summary['best_design']['Cl']
        claimed_cl = claims['final_cl']

        print(f"\nLift Coefficient (Cl):")
        print(f"  Agent claimed: {claimed_cl:.4f}")
        print(f"  S3 shows:      {actual_cl:.4f}")

        diff = abs(claimed_cl - actual_cl)
        if diff < 0.01:
            print(f"  ✓ MATCH - Agent reported correctly")
        else:
            print(f"  ✗ MISMATCH (diff: {diff:.4f}) - Agent hallucinated value")
            comparison['data_hallucinated'] = True

    # Check if agent validated constraint
    if s3_summary['best_design']:
        actual_cl = s3_summary['best_design']['Cl']
        constraint_ok = actual_cl >= 0.30

        print(f"\nConstraint Validation (Cl ≥ 0.30):")
        print(f"  Actual Cl: {actual_cl:.4f}")
        print(f"  Constraint: {'✓ SATISFIED' if constraint_ok else '✗ VIOLATED'}")

        if constraint_ok:
            comparison['constraint_validated'] = True
            print(f"  ✓ Agent should have validated this")
        else:
            print(f"  ⚠ Agent should have rejected this design")

    return comparison


def run_agent_optimization_test():
    """
    Run complete end-to-end agent optimization test.
    """
    print("\n" + "=" * 70)
    print(" BEDROCK AGENT - END-TO-END OPTIMIZATION TEST V2")
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
- MUST call get_next_candidates after baseline
- Report exact values from tool responses (do not invent data)

Please begin the optimization.
"""

    # Invoke agent
    print("\n🚀 Starting agent optimization...")
    start_time = time.time()

    response_text, success = invoke_agent(session_id, prompt)

    elapsed_time = time.time() - start_time

    if not success:
        print("\n✗ Agent invocation failed")
        return False

    print(f"\n⏱️  Execution time: {elapsed_time:.1f} seconds")

    # Wait for S3 consistency
    if not wait_for_s3_consistency(session_id, max_wait=30):
        print("\n⚠ Warning: No S3 data found, but continuing analysis...")

    # Analyze what actually happened
    s3_summary = analyze_s3_results(session_id)

    # Extract what agent claimed
    claims = extract_agent_claims(response_text)

    # Compare claims vs reality
    comparison = compare_claims_vs_reality(claims, s3_summary)

    # Final verdict
    print(f"\n{'=' * 70}")
    print(f"TEST VERDICT")
    print(f"{'=' * 70}")

    success_criteria = [
        ("Agent responded successfully", success),
        ("Tool calls made (designs in S3)", s3_summary['designs_evaluated'] >= 2),
        ("Multiple iterations tracked", s3_summary['iterations_tracked'] >= 1),
        ("Agent mentioned get_next_candidates", claims['mentions_get_next_candidates']),
        ("Constraint satisfied (Cl ≥ 0.30)", s3_summary['constraint_satisfied']),
        ("Agent reported accurate data (no hallucination)", not comparison['data_hallucinated']),
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
        print("\n🎉 SUCCESS! Agent optimization working perfectly!")
        print(f"\nS3 Data: s3://{BUCKET_NAME}/sessions/{session_id}/")
        print(f"\nBest Design Found:")
        if s3_summary['best_design']:
            bd = s3_summary['best_design']
            print(f"  Geometry: {bd['geometry_id']}")
            print(f"  Cd: {bd['Cd']:.5f}")
            print(f"  Cl: {bd['Cl']:.4f}")
            print(f"  L/D: {bd['L_D']:.2f}")
        return True
    else:
        print(f"\n⚠ TEST INCOMPLETE: {total - passed} criteria not met")
        print(f"\nIssues to address:")

        if not claims['mentions_get_next_candidates']:
            print("  - Agent did not call get_next_candidates")
            print("    → Update system prompt to make this mandatory")

        if not s3_summary['constraint_satisfied']:
            print("  - No designs satisfy Cl ≥ 0.30")
            print("    → Check mock aerodynamics formula in run_cfd")

        if comparison['data_hallucinated']:
            print("  - Agent hallucinated data instead of quoting tools")
            print("    → Strengthen anti-hallucination rules in prompt")

        print(f"\nDebugging:")
        print(f"  - Check S3: s3://{BUCKET_NAME}/sessions/{session_id}/")
        print(f"  - Check Lambda logs: aws logs tail /aws/lambda/cfd-* --follow")

        return False


if __name__ == '__main__':
    success = run_agent_optimization_test()
    sys.exit(0 if success else 1)
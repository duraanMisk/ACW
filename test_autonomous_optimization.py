# test_autonomous_optimization.py
"""
Test Autonomous CFD Optimization

Starts a Step Functions execution and monitors progress.
This is the full Day 3 test - autonomous optimization from start to finish!
"""

import boto3
import json
import time
from datetime import datetime

# AWS clients
sfn = boto3.client('stepfunctions', region_name='us-east-1')

# State machine ARN
STATE_MACHINE_ARN = "arn:aws:states:us-east-1:120569639479:stateMachine:cfd-optimization-workflow"


def start_optimization(cl_min=0.30, max_iter=3):
    """Start autonomous optimization execution"""

    execution_name = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print("=" * 60)
    print("🚀 Starting Autonomous CFD Optimization")
    print("=" * 60)
    print(f"Execution name: {execution_name}")
    print(f"Objective: Minimize Cd")
    print(f"Constraint: Cl >= {cl_min}")
    print(f"Max iterations: {max_iter}")
    print("=" * 60)

    # Start execution
    response = sfn.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=execution_name,
        input=json.dumps({
            'objective': 'minimize_cd',
            'cl_min': cl_min,
            'reynolds': 500000,
            'max_iter': max_iter
        })
    )

    execution_arn = response['executionArn']
    print(f"\n✓ Execution started!")
    print(f"ARN: {execution_arn}\n")

    return execution_arn


def monitor_execution(execution_arn):
    """Monitor execution progress with real-time updates"""

    print("📊 Monitoring execution...")
    print("-" * 60)

    last_status = None
    iteration = 0

    while True:
        # Get execution status
        response = sfn.describe_execution(executionArn=execution_arn)
        status = response['status']

        # Print status update if changed
        if status != last_status:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] Status: {status}")
            last_status = status

        if status == 'RUNNING':
            # Try to parse current state from execution history
            try:
                history = sfn.get_execution_history(
                    executionArn=execution_arn,
                    maxResults=10,
                    reverseOrder=True
                )

                for event in history['events']:
                    if event['type'] == 'TaskStateEntered':
                        state_name = event['stateEnteredEventDetails']['name']
                        if 'Iteration' in state_name or 'Agent' in state_name:
                            timestamp = datetime.now().strftime('%H:%M:%S')
                            print(f"[{timestamp}] → {state_name}")
            except:
                pass

            time.sleep(5)
        else:
            break

    print("-" * 60)

    # Final status
    if status == 'SUCCEEDED':
        print("\n✅ OPTIMIZATION COMPLETED SUCCESSFULLY!\n")

        # Parse final output
        output = json.loads(response.get('output', '{}'))

        if 'body' in output:
            report = output['body']

            print("=" * 60)
            print("📋 OPTIMIZATION RESULTS")
            print("=" * 60)

            if 'optimization_summary' in report:
                summary = report['optimization_summary']
                print(f"\nIterations: {summary.get('total_iterations', 'N/A')}")
                print(f"Designs Evaluated: {summary.get('designs_evaluated', 'N/A')}")
                print(f"Reason: {summary.get('convergence_reason', 'N/A')}")

            if 'best_design' in report:
                design = report['best_design']
                print(f"\n🏆 Best Design: {design.get('geometry_id', 'N/A')}")
                print(f"   Cd (drag):  {design.get('Cd', 'N/A'):.5f}")
                print(f"   Cl (lift):  {design.get('Cl', 'N/A'):.4f}")
                print(f"   L/D ratio:  {design.get('L_D', 'N/A'):.2f}")

            if 'performance' in report:
                perf = report['performance']
                print(f"\n📈 Performance:")
                print(f"   Initial Cd: {perf.get('initial_cd', 'N/A'):.5f}")
                print(f"   Final Cd:   {perf.get('final_cd', 'N/A'):.5f}")
                print(f"   Improvement: {perf.get('improvement_pct', 'N/A'):.2f}%")

                constraint = perf.get('constraint_satisfied', False)
                print(f"\n   Constraint (Cl >= {perf.get('constraint_cl_min', 0.30)}):")
                print(f"   {'✅ SATISFIED' if constraint else '❌ VIOLATED'}")
                print(f"   Achieved Cl: {perf.get('achieved_cl', 'N/A'):.4f}")

            print("\n" + "=" * 60)

        return True

    elif status == 'FAILED':
        print("\n❌ OPTIMIZATION FAILED!\n")
        error = response.get('error', 'Unknown error')
        cause = response.get('cause', 'Unknown cause')
        print(f"Error: {error}")
        print(f"Cause: {cause}")
        return False

    elif status == 'TIMED_OUT':
        print("\n⏱️ OPTIMIZATION TIMED OUT")
        return False

    elif status == 'ABORTED':
        print("\n⛔ OPTIMIZATION ABORTED")
        return False

    return False


def main():
    try:
        # Start optimization
        execution_arn = start_optimization(cl_min=0.30, max_iter=3)

        # Monitor until complete
        success = monitor_execution(execution_arn)

        if success:
            print("\n🎉 Day 3 Test: PASSED!")
            print("\nThe system successfully completed autonomous optimization!")
            print("Next steps: CLI interface (Day 4)")
        else:
            print("\n⚠️ Day 3 Test: Issues encountered")
            print("Check CloudWatch logs for details")
            print(f"Execution ARN: {execution_arn}")

    except KeyboardInterrupt:
        print("\n\n⚠️ Monitoring interrupted by user")
        print("The optimization is still running in the background")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
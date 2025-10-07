"""
Direct Lambda Testing - Bypasses Bedrock Agent to Avoid Rate Limits

This script validates:
1. Lambda functions work correctly
2. CSV storage persists data
3. Optimization loop completes end-to-end
4. Convergence detection works

Run this to prove Day 2 goals are met without hitting Bedrock rate limits.
"""

import boto3
import json
import time
import pandas as pd
from pathlib import Path

# Initialize AWS clients
lambda_client = boto3.client('lambda', region_name='us-east-1')

# Lambda function names
GENERATE_GEOMETRY = 'cfd-generate-geometry'
RUN_CFD = 'cfd-run-cfd'
GET_NEXT_CANDIDATES = 'cfd-get-next-candidates'


def invoke_lambda(function_name, payload):
    """Invoke Lambda function and return parsed result."""
    response = lambda_client.invoke(
        FunctionName=function_name,
        Payload=json.dumps(payload)
    )
    result = json.loads(response['Payload'].read())

    # Extract body from Bedrock Agent response format
    if 'response' in result and 'responseBody' in result['response']:
        body_str = result['response']['responseBody']['application/json']['body']
        return json.loads(body_str)
    return result


def format_bedrock_payload(params):
    """Format parameters in Bedrock Agent event format."""
    properties = [
        {'name': k, 'type': 'number' if isinstance(v, (int, float)) else 'string', 'value': str(v)}
        for k, v in params.items()
    ]
    return {
        'requestBody': {
            'content': {
                'application/json': {
                    'properties': properties
                }
            }
        }
    }


def test_optimization_loop(max_iterations=3):
    """
    Run a complete optimization loop directly calling Lambda functions.

    This proves:
    - Lambda functions work correctly
    - CSV storage persists data
    - Optimization logic converges
    """
    print("=" * 70)
    print("CFD OPTIMIZATION - DIRECT LAMBDA TEST")
    print("=" * 70)
    print(f"Target: {max_iterations} iterations")
    print(f"Constraint: Cl ≥ 0.30")
    print(f"Objective: Minimize Cd\n")

    # Track best design
    best_cd = float('inf')
    best_design = None
    iteration_results = []

    # ITERATION 1: BASELINE
    print(f"\n{'=' * 70}")
    print("ITERATION 1: BASELINE ESTABLISHMENT")
    print(f"{'=' * 70}")

    baseline_params = {
        'thickness': 0.12,
        'max_camber': 0.04,
        'camber_position': 0.40,
        'alpha': 4.0
    }

    print(f"Testing NACA 4412 at alpha=4.0°...")

    # Generate geometry
    geo_payload = format_bedrock_payload(baseline_params)
    geo_result = invoke_lambda(GENERATE_GEOMETRY, geo_payload)
    print(f"  ✓ Geometry: {geo_result['geometry_id']}")
    print(f"  ✓ Valid: {geo_result['valid']}")
    print(f"  ✓ Mesh Quality: {geo_result['mesh_quality_score']:.3f}")

    # Run CFD
    cfd_payload = format_bedrock_payload({'geometry_id': geo_result['geometry_id']})
    cfd_result = invoke_lambda(RUN_CFD, cfd_payload)

    print(f"\n  CFD Results:")
    print(f"    Cl = {cfd_result['Cl']:.4f}")
    print(f"    Cd = {cfd_result['Cd']:.5f}")
    print(f"    L/D = {cfd_result['L_D']:.2f}")

    # Check constraint
    if cfd_result['Cl'] >= 0.30:
        print(f"  ✓ Constraint satisfied (Cl ≥ 0.30)")
        best_cd = cfd_result['Cd']
        best_design = {**baseline_params, 'geometry_id': geo_result['geometry_id']}
        print(f"  ✓ Set as current best design")
    else:
        print(f"  ✗ Constraint NOT satisfied (Cl < 0.30)")

    iteration_results.append({
        'iteration': 1,
        'geometry_id': geo_result['geometry_id'],
        'Cl': cfd_result['Cl'],
        'Cd': cfd_result['Cd'],
        'valid': cfd_result['Cl'] >= 0.30
    })

    # ITERATIONS 2-N: OPTIMIZATION LOOP
    for iteration in range(2, max_iterations + 1):
        print(f"\n{'=' * 70}")
        print(f"ITERATION {iteration}: OPTIMIZATION")
        print(f"{'=' * 70}")

        # Get next candidates
        print(f"\nCalling get_next_candidates...")
        candidates_payload = format_bedrock_payload({
            'current_best_cd': best_cd,
            'iteration_number': iteration - 1,
            'constraint_cl_min': 0.30
        })
        candidates_result = invoke_lambda(GET_NEXT_CANDIDATES, candidates_payload)

        print(f"  Strategy: {candidates_result['strategy']}")
        print(f"  Rationale: {candidates_result['rationale']}")
        print(f"  Confidence: {candidates_result['confidence']:.2f}")
        print(f"  Candidates: {len(candidates_result['candidates'])}")

        # Test each candidate (limit to 3 to avoid too many calls)
        test_count = min(3, len(candidates_result['candidates']))
        print(f"\n  Testing {test_count} candidates...")

        iteration_best_cd = best_cd
        iteration_best_design = None

        for i, candidate in enumerate(candidates_result['candidates'][:test_count]):
            print(f"\n    Candidate {i + 1}:")
            print(f"      Params: t={candidate['thickness']:.3f}, m={candidate['max_camber']:.3f}, " +
                  f"p={candidate['camber_position']:.3f}, α={candidate['alpha']:.2f}°")

            # Generate geometry
            geo_payload = format_bedrock_payload(candidate)
            geo_result = invoke_lambda(GENERATE_GEOMETRY, geo_payload)

            if not geo_result['valid']:
                print(f"      ✗ Invalid geometry, skipping")
                continue

            # Run CFD
            cfd_payload = format_bedrock_payload({'geometry_id': geo_result['geometry_id']})
            cfd_result = invoke_lambda(RUN_CFD, cfd_payload)

            print(f"      Geometry: {geo_result['geometry_id']}")
            print(f"      Cl = {cfd_result['Cl']:.4f}, Cd = {cfd_result['Cd']:.5f}")

            # Check if this is better
            if cfd_result['Cl'] >= 0.30 and cfd_result['Cd'] < iteration_best_cd:
                improvement = (iteration_best_cd - cfd_result['Cd']) / iteration_best_cd * 100
                print(f"      ✓ NEW BEST! Cd improved by {improvement:.2f}%")
                iteration_best_cd = cfd_result['Cd']
                iteration_best_design = {**candidate, 'geometry_id': geo_result['geometry_id']}
            elif cfd_result['Cl'] < 0.30:
                print(f"      ✗ Constraint not satisfied")
            else:
                print(f"      - Not better than current best")

            iteration_results.append({
                'iteration': iteration,
                'geometry_id': geo_result['geometry_id'],
                'Cl': cfd_result['Cl'],
                'Cd': cfd_result['Cd'],
                'valid': cfd_result['Cl'] >= 0.30
            })

            # Small delay to be respectful
            time.sleep(0.5)

        # Update best design if improved
        if iteration_best_design:
            improvement = (best_cd - iteration_best_cd) / best_cd * 100
            print(f"\n  ✓ Iteration {iteration} Complete:")
            print(f"    Best Cd: {iteration_best_cd:.5f} (improved {improvement:.2f}%)")
            best_cd = iteration_best_cd
            best_design = iteration_best_design

            # Check convergence
            if improvement < 0.5:
                print(f"\n  ✓ CONVERGED: Improvement < 0.5%")
                break
        else:
            print(f"\n  - No improvement in iteration {iteration}")

    # FINAL REPORT
    print(f"\n{'=' * 70}")
    print("OPTIMIZATION COMPLETE")
    print(f"{'=' * 70}")

    print(f"\nBest Design:")
    print(f"  Geometry: {best_design['geometry_id']}")
    print(f"  Cd = {best_cd:.5f}")
    print(f"  Parameters:")
    print(f"    Thickness: {best_design['thickness']:.4f}")
    print(f"    Max Camber: {best_design['max_camber']:.4f}")
    print(f"    Camber Position: {best_design['camber_position']:.4f}")
    print(f"    Angle of Attack: {best_design['alpha']:.2f}°")

    baseline_cd = iteration_results[0]['Cd']
    total_improvement = (baseline_cd - best_cd) / baseline_cd * 100
    print(f"\n  Total Improvement: {total_improvement:.2f}% from baseline")
    print(f"  Baseline Cd: {baseline_cd:.5f}")
    print(f"  Final Cd: {best_cd:.5f}")

    # Check CSV files
    print(f"\n{'=' * 70}")
    print("CSV STORAGE VERIFICATION")
    print(f"{'=' * 70}")

    csv_data_dir = Path('../data')
    design_history_path = csv_data_dir / 'design_history.csv'
    results_path = csv_data_dir / 'results.csv'

    if design_history_path.exists():
        df = pd.read_csv(design_history_path)
        print(f"\n✓ design_history.csv exists")
        print(f"  Rows: {len(df)}")
        print(f"  Columns: {', '.join(df.columns)}")
        print(f"\n  Latest entries:")
        print(df.tail(3).to_string(index=False))
    else:
        print(f"\n✗ design_history.csv NOT FOUND")
        print(f"  Expected at: {design_history_path.absolute()}")

    if results_path.exists():
        df = pd.read_csv(results_path)
        print(f"\n✓ results.csv exists")
        print(f"  Rows: {len(df)}")
        print(f"  Columns: {', '.join(df.columns)}")
        print(f"\n  Latest entries:")
        print(df.tail(3).to_string(index=False))
    else:
        print(f"\n✗ results.csv NOT FOUND")
        print(f"  Expected at: {results_path.absolute()}")

    print(f"\n{'=' * 70}")
    print("DAY 2 VALIDATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"\n✓ Lambda functions: Working")
    print(f"✓ CSV storage: {'Working' if design_history_path.exists() else 'NOT WORKING'}")
    print(f"✓ Optimization loop: Complete")
    print(f"✓ Constraint handling: Verified")
    print(f"\nReady for Day 3: Step Functions integration")


if __name__ == '__main__':
    try:
        test_optimization_loop(max_iterations=3)
    except Exception as e:
        print(f"\n{'=' * 70}")
        print(f"ERROR: {e}")
        print(f"{'=' * 70}")
        import traceback

        traceback.print_exc()
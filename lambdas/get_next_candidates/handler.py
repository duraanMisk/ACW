"""
Lambda function for optimization candidate generation with S3 storage integration.
Uses trust-region strategy and reads design history from S3.
"""

import json
import random
import os
from datetime import datetime

# Import S3 storage modules
try:
    from storage_s3 import S3DesignHistoryStorage, S3ResultsStorage
    from session_manager import SessionManager
    S3_ENABLED = True
except ImportError:
    print("WARNING: S3 storage modules not available")
    S3_ENABLED = False


def get_optimization_strategy(iteration_number):
    """
    Determine optimization strategy based on iteration number.

    Returns:
        (strategy: str, trust_radius: float)
    """
    if iteration_number <= 2:
        return "explore", 0.015
    elif iteration_number <= 5:
        return "exploit", 0.010
    else:
        return "refine", 0.005


def clip_parameter(value, min_val, max_val):
    """Clip parameter to valid bounds."""
    return max(min_val, min(max_val, value))


def generate_exploration_candidates(num_candidates=4):
    """
    Generate diverse candidates for early exploration.
    """
    candidates = []

    for i in range(num_candidates):
        thickness = random.uniform(0.10, 0.14)
        max_camber = random.uniform(0.03, 0.06)
        camber_position = random.uniform(0.35, 0.45)
        alpha = random.uniform(1.5, 3.5)

        candidates.append({
            'thickness': round(thickness, 4),
            'max_camber': round(max_camber, 4),
            'camber_position': round(camber_position, 4),
            'alpha': round(alpha, 4)
        })

    # Add one "wildcard" for diversity
    candidates.append({
        'thickness': round(random.uniform(0.08, 0.20), 4),
        'max_camber': round(random.uniform(0.0, 0.08), 4),
        'camber_position': round(random.uniform(0.2, 0.6), 4),
        'alpha': round(random.uniform(-2, 10), 4)
    })

    return candidates


def generate_trust_region_candidates(best_design, trust_radius, constraint_cl_min, num_candidates=4):
    """
    Generate candidates around the best design using trust-region method.
    """
    if not best_design:
        return generate_exploration_candidates(num_candidates)

    candidates = []

    for i in range(num_candidates):
        thickness = best_design.get('thickness', 0.12) + random.uniform(-trust_radius, trust_radius)
        max_camber = best_design.get('max_camber', 0.04) + random.uniform(-trust_radius, trust_radius)
        camber_position = best_design.get('camber_position', 0.40) + random.uniform(-trust_radius, trust_radius)
        alpha = best_design.get('alpha', 2.0) + random.uniform(-trust_radius * 50, trust_radius * 50)

        # Clip to valid bounds
        thickness = clip_parameter(thickness, 0.08, 0.20)
        max_camber = clip_parameter(max_camber, 0.0, 0.08)
        camber_position = clip_parameter(camber_position, 0.2, 0.6)
        alpha = clip_parameter(alpha, -2, 10)

        candidates.append({
            'thickness': round(thickness, 4),
            'max_camber': round(max_camber, 4),
            'camber_position': round(camber_position, 4),
            'alpha': round(alpha, 4)
        })

    return candidates


def analyze_design_history_s3(storage):
    """
    Analyze design history from S3 to find best design.

    Returns:
        dict with best_design, best_cd, best_cl, iteration_count
    """
    try:
        designs = storage.read_all_designs()

        if not designs:
            return {
                'best_design': None,
                'best_cd': None,
                'best_cl': None,
                'iteration_count': 0
            }

        # Filter for converged designs only
        converged = [d for d in designs if d.get('converged', False)]

        if not converged:
            return {
                'best_design': None,
                'best_cd': None,
                'best_cl': None,
                'iteration_count': len(designs)
            }

        # Find design with lowest Cd
        best = min(converged, key=lambda d: d.get('Cd', float('inf')))

        best_design = {
            'thickness': best['thickness'],
            'max_camber': best['max_camber'],
            'camber_position': best['camber_position'],
            'alpha': best['alpha']
        }

        return {
            'best_design': best_design,
            'best_cd': best['Cd'],
            'best_cl': best['Cl'],
            'iteration_count': len(designs)
        }

    except Exception as e:
        print(f"Error analyzing history: {e}")
        return {
            'best_design': None,
            'best_cd': None,
            'best_cl': None,
            'iteration_count': 0
        }


def lambda_handler(event, context):
    """
    Lambda handler for candidate generation with S3 integration.
    """
    print(f"Received event: {json.dumps(event)}")

    try:
        # === EXTRACT PARAMETERS FROM BEDROCK AGENT FORMAT ===
        request_body = event.get('requestBody', {})
        content = request_body.get('content', {})
        app_json = content.get('application/json', {})
        properties = app_json.get('properties', [])

        # Convert properties list to dict
        params = {}
        for prop in properties:
            name = prop.get('name')
            value = prop.get('value')
            if name and value is not None:
                params[name] = value

        print(f"Extracted parameters: {params}")

        # === VALIDATE REQUIRED PARAMETERS ===
        iteration_number = int(params.get('iteration_number', 1))
        current_best_cd = float(params.get('current_best_cd', 0.015))
        constraint_cl_min = float(params.get('constraint_cl_min', 0.30))
        session_id = params.get('session_id')  # NEW: Get session ID

        # Best design is optional
        best_design = None
        if 'best_design' in params:
            try:
                best_design = json.loads(params['best_design'])
            except:
                best_design = None

        # === READ DESIGN HISTORY FROM S3 ===
        history_analysis = None
        if S3_ENABLED and session_id:
            try:
                storage = S3DesignHistoryStorage(session_id)
                history_analysis = analyze_design_history_s3(storage)
                print(f"History analysis from S3: {history_analysis}")

                # Use historical best if we don't have one passed in
                if not best_design and history_analysis['best_design']:
                    best_design = history_analysis['best_design']
                    current_best_cd = history_analysis['best_cd']
                    print(f"✓ Retrieved best design from S3: Cd={current_best_cd:.5f}")

            except Exception as e:
                print(f"WARNING: Could not read design history from S3: {e}")
        elif not session_id:
            print(f"⚠ Warning: No session_id provided, cannot read S3 history")

        # === DETERMINE OPTIMIZATION STRATEGY ===
        strategy, trust_radius = get_optimization_strategy(iteration_number)
        print(f"Strategy: {strategy}, Trust radius: {trust_radius}")

        # === GENERATE CANDIDATES ===
        if strategy == "explore":
            candidates = generate_exploration_candidates(num_candidates=4)
            rationale = f"Early exploration phase - sampling diverse design space"
            confidence = 0.6
        else:
            candidates = generate_trust_region_candidates(
                best_design,
                trust_radius,
                constraint_cl_min,
                num_candidates=4
            )
            rationale = f"Trust-region {strategy} (radius={trust_radius:.4f}) around best design"
            confidence = 0.7 + iteration_number * 0.05

        result = {
            'candidates': candidates,
            'strategy': strategy,
            'rationale': rationale,
            'confidence': min(0.95, round(confidence, 2))
        }

        print(f"Generated {len(candidates)} candidates with strategy '{strategy}'")

        # === PERSIST ITERATION SUMMARY TO S3 ===
        if S3_ENABLED and session_id:
            try:
                results_storage = S3ResultsStorage(session_id)

                iteration_data = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'iteration': iteration_number,
                    'candidate_count': len(candidates),
                    'best_cd': current_best_cd,
                    'best_geometry_id': best_design.get('geometry_id', 'N/A') if best_design else 'N/A',
                    'strategy': strategy,
                    'trust_radius': trust_radius,
                    'confidence': result['confidence']
                }

                results_storage.write_result(iteration_data)
                print(f"✓ Wrote iteration summary to S3 (session: {session_id})")

                # Update session metadata
                manager = SessionManager(session_id)
                manager.update_session({
                    'current_iteration': iteration_number
                })

            except Exception as storage_error:
                print(f"⚠ Warning: Failed to write to S3: {storage_error}")
                # Continue anyway

        # === RETURN RESPONSE ===
        return create_success_response(result)

    except Exception as e:
        print(f"ERROR in lambda_handler: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_error_response(f"Candidate generation failed: {str(e)}")


def create_success_response(result):
    """Format successful response for Bedrock Agent."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': 'get-next-candidates',
            'apiPath': '/get_next_candidates',
            'httpMethod': 'POST',
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {
                    'body': json.dumps(result)
                }
            }
        }
    }


def create_error_response(error_message):
    """Format error response for Bedrock Agent."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': 'get-next-candidates',
            'apiPath': '/get_next_candidates',
            'httpMethod': 'POST',
            'httpStatusCode': 400,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({
                        'error': error_message
                    })
                }
            }
        }
    }
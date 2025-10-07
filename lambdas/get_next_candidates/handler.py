"""
Lambda function for optimization candidate generation with CSV storage integration.
Uses trust-region strategy and reads design history.
"""

import json
import random
import os
import sys
from datetime import datetime

# Add shared directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from storage import DesignHistoryStorage, ResultsStorage

    STORAGE_ENABLED = True
except ImportError:
    print("WARNING: Storage module not available, running without persistence")
    STORAGE_ENABLED = False


def get_optimization_strategy(iteration_number):
    """
    Determine optimization strategy based on iteration number.

    Strategy evolution:
    - Early (1-2): Explore - broad sampling
    - Middle (3-5): Exploit - focus on promising regions
    - Late (6+): Refine - local optimization

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

    Samples broadly across the design space to find promising regions.
    """
    candidates = []

    for i in range(num_candidates):
        # Random sampling with slight bias toward middle of ranges
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

    Args:
        best_design: dict with thickness, max_camber, camber_position, alpha
        trust_radius: float, how far to search from best design
        constraint_cl_min: float, minimum Cl requirement
        num_candidates: int, number of candidates to generate

    Returns:
        list of candidate dicts
    """
    candidates = []

    # If we don't have a best design yet, fall back to exploration
    if not best_design:
        return generate_exploration_candidates(num_candidates)

    for i in range(num_candidates):
        # Perturb each parameter within trust region
        thickness = best_design.get('thickness', 0.12) + random.uniform(-trust_radius, trust_radius)
        max_camber = best_design.get('max_camber', 0.04) + random.uniform(-trust_radius, trust_radius)
        camber_position = best_design.get('camber_position', 0.40) + random.uniform(-trust_radius, trust_radius)
        alpha = best_design.get('alpha', 2.0) + random.uniform(-trust_radius * 50,
                                                               trust_radius * 50)  # Larger range for alpha

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


def analyze_design_history(storage):
    """
    Analyze design history to find best design and iteration info.

    Returns:
        dict with best_design, best_cd, best_cl, iteration_count
    """
    try:
        history_df = storage.read_design_history()

        if history_df.empty:
            return {
                'best_design': None,
                'best_cd': None,
                'best_cl': None,
                'iteration_count': 0
            }

        # Filter for converged designs only
        converged = history_df[history_df['converged'] == True]

        if converged.empty:
            return {
                'best_design': None,
                'best_cd': None,
                'best_cl': None,
                'iteration_count': len(history_df)
            }

        # Find design with lowest Cd that satisfies constraint
        # (assumes constraint_cl_min = 0.30, will be validated by agent)
        best_idx = converged['Cd'].idxmin()
        best_row = converged.loc[best_idx]

        best_design = {
            'thickness': float(best_row['thickness']),
            'max_camber': float(best_row['max_camber']),
            'camber_position': float(best_row['camber_position']),
            'alpha': float(best_row['alpha'])
        }

        return {
            'best_design': best_design,
            'best_cd': float(best_row['Cd']),
            'best_cl': float(best_row['Cl']),
            'iteration_count': len(history_df)
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
    Lambda handler for candidate generation.

    Bedrock Agent sends parameters in this format:
    {
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "current_best_cd", "value": "0.0142"},
                        {"name": "iteration_number", "value": "2"},
                        {"name": "constraint_cl_min", "value": "0.30"},
                        {"name": "best_design", "value": "{...}"}  // optional
                    ]
                }
            }
        }
    }
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

        # Best design is optional (might not exist yet)
        best_design = None
        if 'best_design' in params:
            try:
                best_design = json.loads(params['best_design'])
            except:
                best_design = None

        # === READ DESIGN HISTORY (if available) ===
        history_analysis = None
        if STORAGE_ENABLED:
            try:
                storage = DesignHistoryStorage()
                history_analysis = analyze_design_history(storage)
                print(f"History analysis: {history_analysis}")

                # Use historical best if we don't have one passed in
                if not best_design and history_analysis['best_design']:
                    best_design = history_analysis['best_design']
                    current_best_cd = history_analysis['best_cd']

            except Exception as e:
                print(f"WARNING: Could not read design history: {e}")

        # === DETERMINE OPTIMIZATION STRATEGY ===
        strategy, trust_radius = get_optimization_strategy(iteration_number)

        print(f"Strategy: {strategy}, Trust radius: {trust_radius}")

        # === GENERATE CANDIDATES ===
        if strategy == "explore":
            candidates = generate_exploration_candidates(num_candidates=4)
            rationale = f"Early exploration phase - sampling diverse design space (includes 1 wildcard for diversity)"
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

        # === PERSIST ITERATION SUMMARY TO RESULTS CSV ===
        if STORAGE_ENABLED:
            try:
                results_storage = ResultsStorage()

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
                print(f"Successfully wrote iteration summary to results.csv")

            except Exception as storage_error:
                print(f"WARNING: Failed to write to results.csv: {storage_error}")
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


# For local testing
if __name__ == "__main__":
    # Test event
    test_event = {
        'requestBody': {
            'content': {
                'application/json': {
                    'properties': [
                        {'name': 'current_best_cd', 'value': '0.0142'},
                        {'name': 'iteration_number', 'value': '3'},
                        {'name': 'constraint_cl_min', 'value': '0.30'}
                    ]
                }
            }
        }
    }

    result = lambda_handler(test_event, None)
    print("\n=== TEST RESULT ===")
    print(json.dumps(result, indent=2))
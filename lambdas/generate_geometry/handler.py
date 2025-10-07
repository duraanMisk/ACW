"""
Lambda function for airfoil geometry generation with CSV storage integration.
"""

import json
import random
import os
import sys
from datetime import datetime

# Add shared directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from storage import DesignHistoryStorage

    STORAGE_ENABLED = True
except ImportError:
    print("WARNING: Storage module not available, running without persistence")
    STORAGE_ENABLED = False


def validate_naca_parameters(thickness, max_camber, camber_position, alpha):
    """
    Validate NACA 4-series parameters.

    Args:
        thickness: Airfoil thickness as fraction of chord (0.08-0.20)
        max_camber: Maximum camber as fraction of chord (0.0-0.08)
        camber_position: Position of max camber as fraction (0.2-0.6)
        alpha: Angle of attack in degrees (-2 to 10)

    Returns:
        (valid: bool, warnings: list)
    """
    warnings = []
    valid = True

    # Check thickness bounds
    if thickness < 0.08 or thickness > 0.20:
        warnings.append(f"Thickness {thickness:.3f} outside recommended range [0.08, 0.20]")
        valid = False
    elif thickness > 0.15:
        warnings.append("High thickness may cause flow separation")

    # Check camber bounds
    if max_camber < 0.0 or max_camber > 0.08:
        warnings.append(f"Max camber {max_camber:.3f} outside valid range [0.0, 0.08]")
        valid = False
    elif max_camber > 0.06:
        warnings.append("High camber increases drag and may cause separation")

    # Check camber position bounds
    if camber_position < 0.2 or camber_position > 0.6:
        warnings.append(f"Camber position {camber_position:.2f} outside valid range [0.2, 0.6]")
        valid = False
    elif camber_position < 0.3:
        warnings.append("Forward camber position may cause leading edge separation")

    # Check angle of attack bounds
    if alpha < -2 or alpha > 10:
        warnings.append(f"Angle of attack {alpha}° outside valid range [-2, 10]")
        valid = False
    elif alpha > 8:
        warnings.append("High angle of attack near stall region")

    return valid, warnings


def generate_geometry_id(thickness, max_camber, camber_position, alpha):
    """
    Generate NACA 4-series identifier.

    Format: NACA{m}{p}{tt}_a{alpha}
    Example: NACA4412_a2.0

    where:
        m = max camber in % of chord (first digit)
        p = position of max camber in tenths of chord (second digit)
        tt = thickness in % of chord (last two digits)
        alpha = angle of attack
    """
    m_digit = int(max_camber * 100)
    p_digit = int(camber_position * 10)
    t_digits = int(thickness * 100)

    # Format as NACA 4-series
    naca_code = f"NACA{m_digit}{p_digit}{t_digits:02d}"
    geometry_id = f"{naca_code}_a{alpha:.1f}"

    return geometry_id


def calculate_mesh_quality(thickness, max_camber, camber_position):
    """
    Simulate mesh quality score based on geometry complexity.

    Factors:
    - Thinner airfoils are harder to mesh well (sharp trailing edge)
    - High camber creates mesh challenges
    - Extreme camber positions affect quality

    Returns:
        float: Mesh quality score (0.0 to 1.0)
    """
    # Base quality
    quality = 0.90

    # Thickness penalty (very thin is harder to mesh)
    if thickness < 0.10:
        quality -= (0.10 - thickness) * 2.0  # Up to -0.04

    # Camber penalty (high camber is harder to mesh)
    if max_camber > 0.05:
        quality -= (max_camber - 0.05) * 1.5  # Up to -0.045

    # Camber position penalty (extremes are harder)
    position_penalty = abs(camber_position - 0.40) * 0.2
    quality -= position_penalty

    # Add small random variation
    quality += random.uniform(-0.05, 0.05)

    # Clamp to valid range
    quality = max(0.5, min(1.0, quality))

    return quality


def lambda_handler(event, context):
    """
    Lambda handler for geometry generation.

    Bedrock Agent sends parameters in this format:
    {
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "thickness", "type": "number", "value": "0.12"},
                        {"name": "max_camber", "type": "number", "value": "0.04"},
                        {"name": "camber_position", "type": "number", "value": "0.40"},
                        {"name": "alpha", "type": "number", "value": "2.0"}
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
                # Convert string values to appropriate types
                if prop.get('type') == 'number':
                    params[name] = float(value)
                else:
                    params[name] = value

        print(f"Extracted parameters: {params}")

        # === VALIDATE REQUIRED PARAMETERS ===
        required_params = ['thickness', 'max_camber', 'camber_position', 'alpha']
        missing_params = [p for p in required_params if p not in params]

        if missing_params:
            return create_error_response(f"Missing required parameters: {', '.join(missing_params)}")

        thickness = params['thickness']
        max_camber = params['max_camber']
        camber_position = params['camber_position']
        alpha = params['alpha']

        # === VALIDATE PARAMETERS ===
        valid, warnings = validate_naca_parameters(thickness, max_camber, camber_position, alpha)

        # === GENERATE GEOMETRY ===
        geometry_id = generate_geometry_id(thickness, max_camber, camber_position, alpha)
        mesh_quality_score = calculate_mesh_quality(thickness, max_camber, camber_position)

        result = {
            'geometry_id': geometry_id,
            'valid': valid,
            'warnings': warnings,
            'mesh_quality_score': round(mesh_quality_score, 3)
        }

        print(f"Generated geometry: {result}")

        # === PERSIST TO CSV ===
        # Note: We don't write to design_history.csv here because
        # we don't have aerodynamic results yet. The run_cfd function
        # will write the complete record with both geometry and aero data.
        # We could optionally track geometry generation separately if needed.

        if STORAGE_ENABLED:
            try:
                storage = DesignHistoryStorage()

                # Optional: Track geometry generation attempts
                # This helps debug if geometries are being rejected
                geometry_data = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'geometry_id': geometry_id,
                    'thickness': thickness,
                    'max_camber': max_camber,
                    'camber_position': camber_position,
                    'alpha': alpha,
                    'valid': valid,
                    'mesh_quality_score': mesh_quality_score,
                    'warnings': '; '.join(warnings) if warnings else 'None'
                }

                # Write to a separate geometry log (optional)
                # For now, we'll skip this to avoid duplicate data
                # storage.write_geometry(geometry_data)

                print(f"Geometry tracking prepared (not written to avoid duplication)")

            except Exception as storage_error:
                print(f"WARNING: Storage preparation failed: {storage_error}")
                # Continue anyway - storage failure shouldn't break geometry generation

        # === RETURN RESPONSE ===
        return create_success_response(result)

    except Exception as e:
        print(f"ERROR in lambda_handler: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_error_response(f"Geometry generation failed: {str(e)}")


def create_success_response(result):
    """Format successful response for Bedrock Agent."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': 'generate-geometry',
            'apiPath': '/generate_geometry',
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
            'actionGroup': 'generate-geometry',
            'apiPath': '/generate_geometry',
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
                        {'name': 'thickness', 'type': 'number', 'value': '0.12'},
                        {'name': 'max_camber', 'type': 'number', 'value': '0.04'},
                        {'name': 'camber_position', 'type': 'number', 'value': '0.40'},
                        {'name': 'alpha', 'type': 'number', 'value': '2.0'}
                    ]
                }
            }
        }
    }

    result = lambda_handler(test_event, None)
    print("\n=== TEST RESULT ===")
    print(json.dumps(result, indent=2))
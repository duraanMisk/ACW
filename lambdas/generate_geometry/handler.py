"""
Lambda function: generate_geometry
Handles Bedrock Agent format for generating airfoil geometry
"""
import json
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Generate and validate airfoil geometry - Bedrock Agent compatible."""

    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Extract parameters from Bedrock Agent format
        params = {}
        if 'requestBody' in event and 'content' in event['requestBody']:
            content = event['requestBody']['content']
            if 'application/json' in content:
                properties = content['application/json'].get('properties', [])
                for prop in properties:
                    params[prop['name']] = float(prop['value'])

        logger.info(f"Extracted parameters: {params}")

        # Get NACA parameters
        thickness = params.get('thickness', 0.12)
        max_camber = params.get('max_camber', 0.04)
        camber_position = params.get('camber_position', 0.40)
        alpha = params.get('alpha', 2.0)

        # Validate parameters
        valid = True
        warnings = []

        if not (0.08 <= thickness <= 0.20):
            valid = False
            warnings.append(f"Thickness {thickness} outside valid range [0.08, 0.20]")

        if not (0.0 <= max_camber <= 0.08):
            valid = False
            warnings.append(f"Max camber {max_camber} outside valid range [0.0, 0.08]")

        if not (0.2 <= camber_position <= 0.6):
            valid = False
            warnings.append(f"Camber position {camber_position} outside valid range [0.2, 0.6]")

        if not (-2 <= alpha <= 10):
            valid = False
            warnings.append(f"Angle of attack {alpha} outside valid range [-2, 10]")

        # Generate NACA code
        m_digit = int(max_camber * 100)
        p_digit = int(camber_position * 10)
        t_digits = int(thickness * 100)
        naca_code = f"NACA{m_digit}{p_digit}{t_digits:02d}"

        # Create geometry ID with angle of attack
        geometry_id = f"{naca_code}_a{alpha}"

        result = {
            "geometry_id": geometry_id,
            "valid": valid,
            "naca_code": naca_code,
            "parameters": {
                "thickness": thickness,
                "max_camber": max_camber,
                "camber_position": camber_position,
                "alpha": alpha
            }
        }

        if warnings:
            result["warnings"] = warnings

        logger.info(f"Generated geometry: {json.dumps(result)}")

        # Return in Bedrock Agent format
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get('actionGroup', ''),
                "apiPath": event.get('apiPath', ''),
                "httpMethod": event.get('httpMethod', ''),
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps(result)
                    }
                }
            }
        }

    except Exception as e:
        logger.error(f"ERROR in lambda_handler: {str(e)}", exc_info=True)

        # Return error in Bedrock Agent format
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get('actionGroup', ''),
                "apiPath": event.get('apiPath', ''),
                "httpMethod": event.get('httpMethod', ''),
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": str(e)})
                    }
                }
            }
        }
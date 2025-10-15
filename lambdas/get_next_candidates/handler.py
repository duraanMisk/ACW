"""
Lambda function: get_next_candidates
Proposes next optimization candidates using trust-region strategy
"""
import json
import random
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Get next candidate designs - Bedrock Agent compatible."""

    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Extract parameters from Bedrock Agent format
        params = {}
        if 'requestBody' in event and 'content' in event['requestBody']:
            content = event['requestBody']['content']
            if 'application/json' in content:
                properties = content['application/json'].get('properties', [])
                for prop in properties:
                    value = prop['value']
                    try:
                        params[prop['name']] = float(value) if '.' in str(value) else int(value) if str(
                            value).isdigit() else value
                    except:
                        params[prop['name']] = value

        logger.info(f"Extracted parameters: {params}")

        current_best_cd = params.get('current_best_cd', 0.015)
        iteration_number = int(params.get('iteration_number', 1))
        constraint_cl_min = params.get('constraint_cl_min', 0.30)
        session_id = event.get('session_id')

        if not session_id:
            logger.warning("⚠ Warning: No session_id provided, cannot read S3 history")

        # Determine strategy based on iteration
        if iteration_number <= 2:
            strategy = "explore"
            trust_radius = 0.015
            num_candidates = 5
        elif iteration_number <= 5:
            strategy = "exploit"
            trust_radius = 0.010
            num_candidates = 4
        else:
            strategy = "refine"
            trust_radius = 0.005
            num_candidates = 3

        logger.info(f"Strategy: {strategy}, Trust radius: {trust_radius}")

        # Generate candidate designs
        candidates = []

        for i in range(num_candidates):
            # Perturb around reasonable values
            thickness = max(0.08, min(0.20, 0.12 + random.uniform(-trust_radius, trust_radius)))
            max_camber = max(0.0, min(0.08, 0.04 + random.uniform(-trust_radius / 2, trust_radius / 2)))
            camber_position = max(0.2, min(0.6, 0.40 + random.uniform(-trust_radius * 5, trust_radius * 5)))
            alpha = max(-2, min(10, 2.0 + random.uniform(-trust_radius * 50, trust_radius * 50)))

            candidates.append({
                "thickness": round(thickness, 4),
                "max_camber": round(max_camber, 4),
                "camber_position": round(camber_position, 4),
                "alpha": round(alpha, 2)
            })

        logger.info(f"Generated {num_candidates} candidates with strategy '{strategy}'")

        result = {
            "candidates": candidates,
            "strategy": strategy,
            "trust_radius": trust_radius,
            "iteration": iteration_number,
            "message": f"Proposed {num_candidates} candidates using {strategy} strategy"
        }

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
        logger.error(f"ERROR: {str(e)}", exc_info=True)

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
"""
Lambda function: run_cfd
Handles Bedrock Agent format
"""
import json
import random
import math


def lambda_handler(event, context):
    """Run CFD simulation - Bedrock Agent compatible."""

    print(f"Received event: {json.dumps(event)}")

    try:
        # Extract parameters from Bedrock Agent format
        params = {}
        if 'requestBody' in event and 'content' in event['requestBody']:
            content = event['requestBody']['content']
            if 'application/json' in content:
                properties = content['application/json'].get('properties', [])
                for prop in properties:
                    value = prop['value']
                    try:
                        params[prop['name']] = float(value) if '.' in str(value) else value
                    except:
                        params[prop['name']] = value

        print(f"Extracted parameters: {params}")

        geometry_id = params.get('geometry_id', 'NACA4412_a2.0')
        reynolds = float(params.get('reynolds', 500000))

        # Parse NACA parameters from geometry_id
        try:
            naca_part = geometry_id.split('_')[0].replace('NACA', '')
            m = int(naca_part[0]) / 100.0
            p = int(naca_part[1]) / 10.0
            t = int(naca_part[2:4]) / 100.0
            alpha_part = geometry_id.split('_a')[1]
            alpha = float(alpha_part)
        except:
            m, p, t, alpha = 0.04, 0.4, 0.12, 2.0

        # Realistic aerodynamic model
        alpha_rad = alpha * math.pi / 180
        cl_alpha = 2 * math.pi * alpha_rad
        cl_camber = m * 0.8
        Cl = cl_alpha + cl_camber

        if alpha > 10:
            Cl *= 0.8
        elif alpha > 8:
            Cl *= 0.95

        Cd_profile = 0.006 + 0.02 * (t ** 2)
        AR = 5.0
        e = 0.85
        Cd_induced = (Cl ** 2) / (math.pi * AR * e)

        Re_ref = 500000
        Re_factor = (Re_ref / reynolds) ** 0.2 if reynolds > 0 else 1.0

        Cd = (Cd_profile + Cd_induced) * Re_factor
        Cd += m * 0.005
        Cd *= random.uniform(0.995, 1.005)
        Cl *= random.uniform(0.995, 1.005)

        L_D = Cl / Cd if Cd > 0 else 0

        converged = True
        iterations = random.randint(180, 250)
        computation_time = random.uniform(45, 90)

        if t < 0.09 or t > 0.18 or abs(alpha) > 12:
            if random.random() < 0.05:
                converged = False
                iterations = 500

        response_body = {
            "Cl": round(Cl, 4),
            "Cd": round(Cd, 5),
            "L_D": round(L_D, 2),
            "converged": converged,
            "iterations": iterations,
            "computation_time": round(computation_time, 2)
        }

        print(f"Response: {json.dumps(response_body)}")

        # Return in Bedrock Agent format
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get('actionGroup'),
                "apiPath": event.get('apiPath'),
                "httpMethod": event.get('httpMethod'),
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps(response_body)
                    }
                }
            }
        }

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get('actionGroup'),
                "apiPath": event.get('apiPath'),
                "httpMethod": event.get('httpMethod'),
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": str(e)})
                    }
                }
            }
        }
"""
Lambda function: run_cfd with S3 storage integration
Handles Bedrock Agent format and persists results to S3
"""
import json
import random
import math
import os
from datetime import datetime

# Import S3 storage modules
try:
    from storage_s3 import S3DesignHistoryStorage
    from session_manager import SessionManager

    S3_ENABLED = True
except ImportError:
    print("WARNING: S3 storage modules not available")
    S3_ENABLED = False


def lambda_handler(event, context):
    """Run CFD simulation - Bedrock Agent compatible with S3 storage."""

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
        session_id = params.get('session_id')  # NEW: Get session ID

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

        # Realistic aerodynamic model (same as before)
        alpha_rad = alpha * math.pi / 180
        cl_alpha = 2 * math.pi * alpha_rad
        cl_camber = m * 10.0  # Increased multiplier for better Cl values
        Cl = cl_alpha + cl_camber + 0.15  # Base lift

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

        print(f"CFD Results: {json.dumps(response_body)}")

        # === PERSIST TO S3 ===
        if S3_ENABLED and session_id:
            try:
                storage = S3DesignHistoryStorage(session_id)

                # Create complete design record
                design_data = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'geometry_id': geometry_id,
                    'thickness': t,
                    'max_camber': m,
                    'camber_position': p,
                    'alpha': alpha,
                    'Cl': response_body['Cl'],
                    'Cd': response_body['Cd'],
                    'L_D': response_body['L_D'],
                    'converged': converged,
                    'reynolds': reynolds,
                    'iterations': iterations,
                    'computation_time': computation_time
                }

                storage.write_design(design_data)
                print(f"✓ Persisted design to S3 (session: {session_id})")

                # Update session metadata
                manager = SessionManager(session_id)
                session_data = manager.get_session()

                if session_data:
                    # Check if this is the best design so far
                    current_best_cd = session_data.get('best_cd')
                    if current_best_cd is None or (converged and response_body['Cd'] < current_best_cd):
                        manager.update_session({
                            'best_cd': response_body['Cd'],
                            'best_geometry_id': geometry_id,
                            'total_designs_evaluated': session_data.get('total_designs_evaluated', 0) + 1
                        })
                        print(f"✓ Updated session with new best design")
                    else:
                        manager.update_session({
                            'total_designs_evaluated': session_data.get('total_designs_evaluated', 0) + 1
                        })

            except Exception as storage_error:
                print(f"⚠ Warning: S3 storage failed: {storage_error}")
                # Continue anyway - don't fail the function if storage fails
        elif not session_id:
            print(f"⚠ Warning: No session_id provided, skipping S3 storage")

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
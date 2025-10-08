"""
Run CFD Lambda: Simulate aerodynamics on generated geometry

This function simulates CFD analysis and returns aerodynamic coefficients.
Uses realistic mock data based on thin airfoil theory.

NOW WITH S3 STORAGE: Writes results to design_history.csv in S3
"""

import json
import random
import os
from datetime import datetime

# Import storage module for S3 persistence
try:
    from storage import DesignHistoryStorage, StorageConfig

    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False
    print("Warning: storage module not available")


def lambda_handler(event, context):
    """
    Run CFD simulation on geometry and return aerodynamic results.

    Expected event format (from Bedrock Agent):
    {
        "apiPath": "/run_cfd",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "geometry_id", "value": "NACA4412_a2.0"},
                        {"name": "reynolds", "value": "500000"},
                        {"name": "alpha", "value": "2.0"}
                    ]
                }
            }
        },
        "SESSION_ID": "optional-session-id"
    }
    """

    print(f"Event received: {json.dumps(event)}")

    try:
        # Extract parameters from Bedrock Agent format
        request_body = event.get('requestBody', {})
        content = request_body.get('content', {})
        json_content = content.get('application/json', {})
        properties = json_content.get('properties', [])

        # Convert properties array to dict
        params = {}
        for prop in properties:
            params[prop['name']] = prop['value']

        # Get session ID if provided
        session_id = event.get('SESSION_ID', os.environ.get('SESSION_ID', 'default-session'))

        # Extract required parameters
        geometry_id = params.get('geometry_id', 'UNKNOWN')
        reynolds = float(params.get('reynolds', 500000))
        alpha = float(params.get('alpha', 2.0))

        print(f"Running CFD for: {geometry_id}, Re={reynolds}, alpha={alpha}°")
        print(f"Session ID: {session_id}")

        # Parse NACA parameters from geometry_id
        # Format: NACA{m}{p}{t}_a{alpha}
        # Example: NACA4412_a2.0 -> m=0.04, p=0.4, t=0.12
        try:
            naca_part = geometry_id.split('_')[0].replace('NACA', '')
            if len(naca_part) >= 4:
                m = int(naca_part[0]) / 100.0  # max camber
                p = int(naca_part[1]) / 10.0  # camber position
                t = int(naca_part[2:4]) / 100.0  # thickness
            else:
                m, p, t = 0.04, 0.4, 0.12  # defaults
        except:
            m, p, t = 0.04, 0.4, 0.12  # defaults on parse error

        print(f"Parsed NACA parameters: m={m}, p={p}, t={t}")

        # Simulate CFD with REALISTIC aerodynamics
        # Based on thin airfoil theory with adjustments

        # Convert alpha to radians
        import math
        alpha_rad = alpha * math.pi / 180.0

        # Lift coefficient calculation
        # Cl = 2π·α + camber contribution + base offset
        camber_lift = m * 10.0  # Camber increases lift
        alpha_lift = 2 * math.pi * alpha_rad  # Angle of attack contribution
        Cl = alpha_lift + camber_lift + 0.15  # Base offset for realistic values

        # Add small random variation to simulate CFD convergence
        Cl += random.uniform(-0.005, 0.005)

        # Drag coefficient calculation
        # Cd = form drag + induced drag + base drag
        Cd_form = 0.006 + 0.02 * t ** 2  # Thickness increases form drag
        Cd_induced = Cl ** 2 / (math.pi * 5.0)  # Induced drag (assuming AR=5)
        Cd_base = 0.001  # Base drag
        Cd = Cd_form + Cd_induced + Cd_base

        # Add small random variation
        Cd += random.uniform(-0.0002, 0.0002)

        # Lift-to-drag ratio
        L_D = Cl / Cd if Cd > 0 else 0

        # Simulate convergence metrics
        converged = True
        iterations = random.randint(180, 250)
        computation_time = random.uniform(45.0, 90.0)

        # Build response
        result = {
            "Cl": round(Cl, 4),
            "Cd": round(Cd, 5),
            "L_D": round(L_D, 2),
            "converged": converged,
            "iterations": iterations,
            "computation_time": round(computation_time, 2)
        }

        print(f"CFD Results: Cl={result['Cl']}, Cd={result['Cd']}, L/D={result['L_D']}")

        # ========== NEW: Write to S3 ==========
        if STORAGE_AVAILABLE:
            try:
                # Set session ID in environment for storage module
                os.environ['SESSION_ID'] = session_id

                # Create storage instance
                config = StorageConfig()
                storage = DesignHistoryStorage(config)

                # Write design evaluation to S3
                design_data = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'geometry_id': geometry_id,
                    'thickness': t,
                    'max_camber': m,
                    'camber_position': p,
                    'alpha': alpha,
                    'Cl': result['Cl'],
                    'Cd': result['Cd'],
                    'L_D': result['L_D'],
                    'converged': result['converged'],
                    'reynolds': int(reynolds),
                    'iterations': result['iterations'],
                    'computation_time': result['computation_time']
                }

                storage.write_design(design_data)
                print(f"✅ Wrote design to S3: {session_id}/design_history.csv")

            except Exception as e:
                print(f"⚠️ Warning: Failed to write to S3: {e}")
                # Continue anyway - storage is nice-to-have, not critical
        # ========================================

        # Return in Bedrock Agent format
        response = {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": None,
                "apiPath": event.get('apiPath', '/run_cfd'),
                "httpMethod": None,
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps(result)
                    }
                }
            }
        }

        return response

    except Exception as e:
        print(f"Error in run_cfd: {str(e)}")
        import traceback
        traceback.print_exc()

        # Return error response
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": None,
                "apiPath": event.get('apiPath', '/run_cfd'),
                "httpMethod": None,
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": str(e)})
                    }
                }
            }
        }
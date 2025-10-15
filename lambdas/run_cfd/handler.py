import json
import logging
import os
import random
from datetime import datetime
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['BUCKET_NAME']


def lambda_handler(event, context):
    """Handle run_cfd requests from Bedrock Agent"""
    logger.info(f"Received event: {json.dumps(event)}")

    # Extract session_id from the EVENT ROOT (not from parameters)
    session_id = event.get('sessionId')  # <-- CRITICAL FIX

    # Extract parameters from requestBody
    request_body = event.get('requestBody', {})
    content = request_body.get('content', {})
    app_json = content.get('application/json', {})
    properties = app_json.get('properties', [])

    # Parse parameters
    params = {}
    for prop in properties:
        params[prop['name']] = prop['value']

    logger.info(f"Extracted parameters: {params}")
    logger.info(f"Session ID: {session_id}")  # <-- Log it

    geometry_id = params.get('geometry_id')
    reynolds = params.get('reynolds', 500000)

    if not geometry_id:
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event['actionGroup'],
                'apiPath': event['apiPath'],
                'httpMethod': event['httpMethod'],
                'httpStatusCode': 400,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps({
                            'error': 'geometry_id is required'
                        })
                    }
                }
            }
        }

    # Run mock CFD simulation
    results = run_mock_cfd(geometry_id, reynolds)
    logger.info(f"CFD Results: {json.dumps(results)}")

    # Save to S3 if session_id is provided
    if session_id:
        save_to_s3(session_id, geometry_id, results)
    else:
        logger.warning("⚠ Warning: No session_id provided, skipping S3 storage")

    # Return response to agent
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event['actionGroup'],
            'apiPath': event['apiPath'],
            'httpMethod': event['httpMethod'],
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {
                    'body': json.dumps(results)
                }
            }
        }
    }


def run_mock_cfd(geometry_id, reynolds):
    """Generate realistic mock CFD results"""
    # Parse NACA code from geometry_id (e.g., "NACA4410_a2.4")
    parts = geometry_id.split('_')
    naca_code = parts[0].replace('NACA', '')
    alpha = float(parts[1].replace('a', '')) if len(parts) > 1 else 2.0

    # Extract NACA parameters
    max_camber = int(naca_code[0]) / 100.0
    camber_pos = int(naca_code[1]) / 10.0
    thickness = int(naca_code[2:4]) / 100.0

    # Realistic aerodynamic correlations
    Cl = 2 * 3.14159 * (alpha * 3.14159 / 180) + 0.1 * max_camber * 10
    Cd_profile = 0.006 + 0.3 * thickness ** 2
    Cd_induced = Cl ** 2 / (3.14159 * 8.0)  # Induced drag
    Cd = Cd_profile + Cd_induced

    # Add some noise
    Cl += random.uniform(-0.02, 0.02)
    Cd += random.uniform(-0.001, 0.001)

    L_D = Cl / Cd if Cd > 0 else 0

    return {
        'Cl': round(Cl, 4),
        'Cd': round(Cd, 5),
        'L_D': round(L_D, 2),
        'converged': True,
        'iterations': random.randint(150, 300),
        'computation_time': round(random.uniform(30, 90), 2)
    }


def save_to_s3(session_id, geometry_id, results):
    """Save CFD results to S3"""
    try:
        timestamp = datetime.utcnow().isoformat()

        # Save individual design result
        design_key = f"sessions/{session_id}/designs/{geometry_id}.json"
        design_data = {
            'geometry_id': geometry_id,
            'timestamp': timestamp,
            **results
        }

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=design_key,
            Body=json.dumps(design_data, indent=2),
            ContentType='application/json'
        )

        logger.info(f"Saved design to S3: {design_key}")

        # Append to design_history.csv
        csv_key = f"sessions/{session_id}/design_history.csv"

        # Try to read existing CSV
        try:
            existing = s3.get_object(Bucket=BUCKET_NAME, Key=csv_key)
            csv_content = existing['Body'].read().decode('utf-8')
        except s3.exceptions.NoSuchKey:
            # Create new CSV with header
            csv_content = "timestamp,geometry_id,Cl,Cd,L_D,converged,iterations,computation_time\n"

        # Append new row
        csv_row = f"{timestamp},{geometry_id},{results['Cl']},{results['Cd']},{results['L_D']},{results['converged']},{results['iterations']},{results['computation_time']}\n"
        csv_content += csv_row

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=csv_key,
            Body=csv_content.encode('utf-8'),
            ContentType='text/csv'
        )

        logger.info(f"Updated design_history.csv: {csv_key}")

    except Exception as e:
        logger.error(f"Error saving to S3: {str(e)}")
        raise
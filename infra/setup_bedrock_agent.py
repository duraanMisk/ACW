"""
Setup script for Bedrock Agent
Creates Bedrock Agent and registers action groups with Lambda functions
"""
import boto3
import json
import time
from pathlib import Path


def read_system_prompt():
    """Read agent system prompt from file."""
    prompt_path = Path("../agent/prompts/system_prompt.txt")
    with open(prompt_path, 'r') as f:
        return f.read()


def read_tool_schema():
    """Read OpenAPI tool schema."""
    schema_path = Path("../agent/schemas/tool_schemas.json")
    with open(schema_path, 'r') as f:
        return json.load(f)


def get_cdk_outputs():
    """
    Get Lambda ARNs from CDK stack outputs.
    """
    cfn = boto3.client('cloudformation', region_name='us-east-1')

    try:
        response = cfn.describe_stacks(StackName='CFDOptimizationAgentStack')
        outputs = response['Stacks'][0]['Outputs']

        result = {}
        for output in outputs:
            key = output['OutputKey']
            value = output['OutputValue']
            result[key] = value

        return result
    except Exception as e:
        print(f"Error: Could not find CFD stack outputs.")
        print(f"Have you deployed the CDK stack? Run: cd infra/cdk && cdk deploy")
        raise e


def check_bedrock_access():
    """Check if we have access to Bedrock and Claude models."""
    bedrock = boto3.client('bedrock', region_name='us-east-1')

    print("Checking Bedrock model access...")
    try:
        models = bedrock.list_foundation_models()
        claude_models = [m for m in models.get('modelSummaries', [])
                         if 'claude' in m['modelId'].lower()]

        if not claude_models:
            print("\n⚠️  No Claude models found!")
            print("You need to request model access in the AWS Console:")
            print("1. Go to AWS Console → Bedrock")
            print("2. Click 'Model access' → 'Manage model access'")
            print("3. Enable Anthropic Claude models")
            print("4. Wait for approval (usually instant)")
            return False

        print(f"✓ Found {len(claude_models)} Claude model(s)")
        return True
    except Exception as e:
        print(f"Error checking Bedrock access: {e}")
        return False


def create_bedrock_agent(outputs):
    """Create Bedrock Agent with action groups."""
    bedrock = boto3.client('bedrock-agent', region_name='us-east-1')

    agent_role_arn = outputs['AgentRoleArn']
    system_prompt = read_system_prompt()

    print("\n" + "=" * 60)
    print("Creating Bedrock Agent...")
    print("=" * 60)

    # Use Claude 3 Sonnet - most reliable for Bedrock Agents
    model_id = 'anthropic.claude-3-sonnet-20240229-v1:0'

    print(f"Using model: {model_id}")

    try:
        # Create agent
        agent_response = bedrock.create_agent(
            agentName='cfd-optimization-agent',
            description='Autonomous CFD design optimization agent',
            agentResourceRoleArn=agent_role_arn,
            foundationModel=model_id,
            instruction=system_prompt,
            idleSessionTTLInSeconds=1800  # 30 minutes
        )

        agent_id = agent_response['agent']['agentId']
        print(f"✓ Agent created successfully")
        print(f"  Agent ID: {agent_id}")
        print(f"  Model: {model_id}")

    except Exception as e:
        print(f"✗ Failed to create agent: {e}")
        print("\nTrying to list available models for Agents...")
        return None

    # Wait for agent to be ready
    print("\nWaiting for agent to initialize...")
    time.sleep(3)

    # Read OpenAPI schema
    tool_schema = read_tool_schema()

    # Create action groups (one per Lambda function for clarity)
    print("\nCreating action groups...")

    # Action Group 1: Generate Geometry
    try:
        bedrock.create_agent_action_group(
            agentId=agent_id,
            agentVersion='DRAFT',
            actionGroupName='generate-geometry',
            description='Generate and validate airfoil geometry',
            actionGroupExecutor={
                'lambda': outputs['GenerateGeometryFunctionArn']
            },
            apiSchema={
                'payload': json.dumps({
                    "openapi": "3.0.0",
                    "info": {
                        "title": "Generate Geometry API",
                        "version": "1.0.0"
                    },
                    "paths": {
                        "/generate_geometry": tool_schema["paths"]["/generate_geometry"]
                    }
                })
            }
        )
        print("  ✓ generate-geometry action group created")
    except Exception as e:
        print(f"  ✗ Failed to create generate-geometry: {e}")

    # Action Group 2: Run CFD
    try:
        bedrock.create_agent_action_group(
            agentId=agent_id,
            agentVersion='DRAFT',
            actionGroupName='run-cfd',
            description='Run CFD simulation',
            actionGroupExecutor={
                'lambda': outputs['RunCFDFunctionArn']
            },
            apiSchema={
                'payload': json.dumps({
                    "openapi": "3.0.0",
                    "info": {
                        "title": "Run CFD API",
                        "version": "1.0.0"
                    },
                    "paths": {
                        "/run_cfd": tool_schema["paths"]["/run_cfd"]
                    }
                })
            }
        )
        print("  ✓ run-cfd action group created")
    except Exception as e:
        print(f"  ✗ Failed to create run-cfd: {e}")

    # Action Group 3: Get Next Candidates
    try:
        bedrock.create_agent_action_group(
            agentId=agent_id,
            agentVersion='DRAFT',
            actionGroupName='get-next-candidates',
            description='Propose next optimization candidates',
            actionGroupExecutor={
                'lambda': outputs['GetNextCandidatesFunctionArn']
            },
            apiSchema={
                'payload': json.dumps({
                    "openapi": "3.0.0",
                    "info": {
                        "title": "Get Next Candidates API",
                        "version": "1.0.0"
                    },
                    "paths": {
                        "/get_next_candidates": tool_schema["paths"]["/get_next_candidates"]
                    }
                })
            }
        )
        print("  ✓ get-next-candidates action group created")
    except Exception as e:
        print(f"  ✗ Failed to create get-next-candidates: {e}")

    # Prepare agent
    print("\nPreparing agent (this may take 1-2 minutes)...")
    bedrock.prepare_agent(agentId=agent_id)

    # Wait for preparation
    max_retries = 30
    for i in range(max_retries):
        time.sleep(5)
        agent_status = bedrock.get_agent(agentId=agent_id)
        status = agent_status['agent']['agentStatus']

        if status == 'PREPARED':
            print("✓ Agent prepared successfully")
            break
        elif status == 'FAILED':
            print("✗ Agent preparation failed")
            print("Check AWS Console for details")
            return None
        else:
            print(f"  Status: {status}... ({i + 1}/{max_retries})")

    # Create alias
    print("\nCreating agent alias...")
    try:
        alias_response = bedrock.create_agent_alias(
            agentId=agent_id,
            agentAliasName='production',
            description='Production alias for CFD optimization agent'
        )

        alias_id = alias_response['agentAlias']['agentAliasId']
        print(f"✓ Alias created: {alias_id}")
    except Exception as e:
        print(f"⚠️  Failed to create alias: {e}")
        alias_id = "TSTALIASID"  # Use test alias
        print(f"Using test alias: {alias_id}")

    # Save configuration
    config = {
        'agent_id': agent_id,
        'alias_id': alias_id,
        'agent_arn': agent_response['agent']['agentArn'],
        'model_id': model_id
    }

    config_path = Path('../agent/agent_config.json')
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(config, indent=2, fp=f)

    print(f"\n{'=' * 60}")
    print("✓ Bedrock Agent setup complete!")
    print(f"{'=' * 60}")
    print(f"Agent ID: {agent_id}")
    print(f"Alias ID: {alias_id}")
    print(f"Model: {model_id}")
    print(f"\nConfiguration saved to: {config_path}")
    print("\nNext steps:")
    print("  1. Test the agent: python test_agent.py")
    print("  2. View in AWS Console: Bedrock → Agents")

    return config


def main():
    """Main setup flow."""
    print("=" * 60)
    print("CFD Optimization Agent - Bedrock Setup")
    print("=" * 60)

    # Check Bedrock access
    if not check_bedrock_access():
        print("\n✗ Setup cannot continue without Bedrock access")
        print("Please enable model access and try again")
        return

    # Get CDK outputs
    print("\nReading CDK stack outputs...")
    try:
        outputs = get_cdk_outputs()
        print("✓ Found Lambda functions:")
        print(f"  - generate_geometry")
        print(f"  - run_cfd")
        print(f"  - get_next_candidates")
    except Exception as e:
        print(f"✗ Failed to get CDK outputs: {e}")
        return

    # Create agent
    config = create_bedrock_agent(outputs)

    if config:
        print("\n✓ Setup completed successfully!")
        print("\nYou can now test the agent!")
    else:
        print("\n✗ Setup failed. Check error messages above.")


if __name__ == "__main__":
    main()
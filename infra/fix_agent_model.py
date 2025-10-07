"""
Fix Bedrock Agent model identifier
Checks available models and updates agent with correct one
"""
import boto3
import json
from pathlib import Path


def get_available_claude_models():
    """Get list of available Claude models."""
    bedrock = boto3.client('bedrock', region_name='us-east-1')

    response = bedrock.list_foundation_models()
    claude_models = [
        m for m in response.get('modelSummaries', [])
        if 'claude' in m['modelId'].lower()
    ]

    return claude_models


def load_agent_config():
    """Load agent configuration."""
    config_path = Path('../agent/agent_config.json')
    with open(config_path, 'r') as f:
        return json.load(f)


def update_agent_model(agent_id, model_id):
    """Update agent with new model ID."""
    bedrock = boto3.client('bedrock-agent', region_name='us-east-1')

    # Get current agent details
    agent = bedrock.get_agent(agentId=agent_id)
    agent_details = agent['agent']

    # Update agent with new model
    bedrock.update_agent(
        agentId=agent_id,
        agentName=agent_details['agentName'],
        agentResourceRoleArn=agent_details['agentResourceRoleArn'],
        foundationModel=model_id,
        instruction=agent_details['instruction']
    )

    print(f"✓ Agent updated with model: {model_id}")

    # Prepare agent again
    print("Preparing agent...")
    bedrock.prepare_agent(agentId=agent_id)

    import time
    for i in range(20):
        time.sleep(5)
        status = bedrock.get_agent(agentId=agent_id)['agent']['agentStatus']
        if status == 'PREPARED':
            print("✓ Agent prepared successfully")
            break
        print(f"  Status: {status}...")

    # Update config file
    config = load_agent_config()
    config['model_id'] = model_id
    with open('../agent/agent_config.json', 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Config updated")


def main():
    print("=" * 60)
    print("Fix Bedrock Agent Model ID")
    print("=" * 60)

    # Get available models
    print("\nChecking available Claude models...")
    models = get_available_claude_models()

    if not models:
        print("✗ No Claude models found!")
        print("Please enable model access in AWS Console:")
        print("  Bedrock → Model access → Manage model access")
        return

    print(f"\nFound {len(models)} Claude model(s):")
    for i, model in enumerate(models):
        print(f"  {i + 1}. {model['modelId']}")
        print(f"     {model['modelName']}")

    # Common model IDs to try (in order of preference)
    preferred_models = [
        'anthropic.claude-3-5-sonnet-20241022-v2:0',  # Claude 3.5 Sonnet v2
        'anthropic.claude-3-5-sonnet-20240620-v1:0',  # Claude 3.5 Sonnet v1
        'anthropic.claude-3-sonnet-20240229-v1:0',  # Claude 3 Sonnet
        'us.anthropic.claude-3-5-sonnet-20241022-v2:0',  # Cross-region version
    ]

    # Find first available model
    model_to_use = None
    available_ids = [m['modelId'] for m in models]

    for model_id in preferred_models:
        if model_id in available_ids:
            model_to_use = model_id
            break

    if not model_to_use:
        # Use first available Claude model
        model_to_use = available_ids[0]

    print(f"\nSelected model: {model_to_use}")

    # Load agent config
    config = load_agent_config()
    agent_id = config['agent_id']

    print(f"\nUpdating agent {agent_id}...")
    update_agent_model(agent_id, model_to_use)

    print("\n" + "=" * 60)
    print("✓ Agent fixed successfully!")
    print("=" * 60)
    print("\nYou can now test the agent:")
    print("  python test_agent.py")


if __name__ == "__main__":
    main()
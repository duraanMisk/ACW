"""
Update Bedrock Agent System Prompt

This script updates the agent's instruction (system prompt) to the new v3 version
that fixes hallucination and enforces proper workflow.
"""

import boto3
import json
import time
from pathlib import Path

# Configuration
AGENT_ID = 'MXUZMBTQFV'
REGION = 'us-east-1'
PROMPT_FILE = 'agent/prompts/system_prompt.txt'  # Your file name

# Initialize client
bedrock_agent = boto3.client('bedrock-agent', region_name=REGION)


def read_prompt_file(filepath):
    """Read the new system prompt from file."""
    path = Path(filepath)

    if not path.exists():
        print(f"✗ Error: Prompt file not found at {filepath}")
        print(f"  Current directory: {Path.cwd()}")
        return None

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"✓ Read prompt file: {len(content)} characters")
    return content


def get_current_agent_config():
    """Get the current agent configuration."""
    try:
        response = bedrock_agent.get_agent(agentId=AGENT_ID)
        agent = response['agent']

        print(f"\nCurrent Agent Configuration:")
        print(f"  Name: {agent['agentName']}")
        print(f"  Status: {agent['agentStatus']}")
        print(f"  Model: {agent['foundationModel']}")
        print(f"  Current instruction length: {len(agent.get('instruction', ''))} characters")

        return agent

    except Exception as e:
        print(f"✗ Error getting agent: {e}")
        return None


def update_agent_instruction(new_instruction):
    """Update the agent's instruction (system prompt)."""
    try:
        # Get current configuration
        current_agent = get_current_agent_config()
        if not current_agent:
            return False

        print(f"\n📝 Updating agent instruction...")
        print(f"  New instruction length: {len(new_instruction)} characters")

        # Update agent with new instruction
        response = bedrock_agent.update_agent(
            agentId=AGENT_ID,
            agentName=current_agent['agentName'],
            foundationModel=current_agent['foundationModel'],
            instruction=new_instruction,
            agentResourceRoleArn=current_agent['agentResourceRoleArn'],  # Added this!
            description=current_agent.get('description', 'Autonomous CFD design optimization agent'),
            idleSessionTTLInSeconds=current_agent.get('idleSessionTTLInSeconds', 1800)
        )

        print(f"✓ Agent updated successfully")
        print(f"  Status: {response['agent']['agentStatus']}")

        return True

    except Exception as e:
        print(f"✗ Error updating agent: {e}")
        return False


def prepare_agent():
    """Prepare the agent after updating (required for changes to take effect)."""
    try:
        print(f"\n🔄 Preparing agent (this may take 30-60 seconds)...")

        response = bedrock_agent.prepare_agent(agentId=AGENT_ID)

        print(f"  Status: {response['agentStatus']}")
        print(f"  Prepared at: {response['preparedAt']}")

        # Wait for preparation to complete
        max_wait = 60
        for i in range(max_wait):
            time.sleep(1)

            status_response = bedrock_agent.get_agent(agentId=AGENT_ID)
            status = status_response['agent']['agentStatus']

            if status == 'PREPARED':
                print(f"\n✓ Agent prepared successfully!")
                return True
            elif status == 'FAILED':
                print(f"\n✗ Agent preparation failed")
                return False

            if (i + 1) % 10 == 0:
                print(f"  Still preparing... ({i + 1}s)")

        print(f"\n⚠ Preparation taking longer than expected, but may still succeed")
        return True

    except Exception as e:
        print(f"✗ Error preparing agent: {e}")
        return False


def verify_update():
    """Verify the update was successful."""
    try:
        print(f"\n✅ Verifying update...")

        response = bedrock_agent.get_agent(agentId=AGENT_ID)
        agent = response['agent']

        new_instruction = agent.get('instruction', '')

        print(f"  Agent status: {agent['agentStatus']}")
        print(f"  Instruction length: {len(new_instruction)} characters")

        # Check if new prompt has key indicators
        indicators = [
            'NEVER MAKE UP DATA',
            'get_next_candidates',
            'CONSTRAINT VALIDATION',
            'Rule #1',
            'Rule #2'
        ]

        found = [ind for ind in indicators if ind in new_instruction]

        print(f"\n  Key sections found: {len(found)}/{len(indicators)}")
        for ind in found:
            print(f"    ✓ {ind}")

        if len(found) == len(indicators):
            print(f"\n✓ Update verified - new prompt is active")
            return True
        else:
            print(f"\n⚠ Some sections missing - update may not have worked")
            return False

    except Exception as e:
        print(f"✗ Error verifying: {e}")
        return False


def main():
    """Main execution flow."""
    print("=" * 70)
    print("Bedrock Agent Prompt Update Utility")
    print("=" * 70)
    print(f"Agent ID: {AGENT_ID}")
    print(f"Region: {REGION}")
    print(f"Prompt file: {PROMPT_FILE}")
    print("=" * 70)

    # Step 1: Read new prompt
    new_instruction = read_prompt_file(PROMPT_FILE)
    if not new_instruction:
        return False

    # Step 2: Show preview
    print(f"\n📄 Prompt Preview (first 200 chars):")
    print("-" * 70)
    print(new_instruction[:200] + "...")
    print("-" * 70)

    # Step 3: Confirm
    print(f"\n⚠️  This will replace the current agent instruction.")
    response = input("Continue? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("\n❌ Update cancelled")
        return False

    # Step 4: Update agent
    if not update_agent_instruction(new_instruction):
        print("\n❌ Update failed")
        return False

    # Step 5: Prepare agent
    if not prepare_agent():
        print("\n❌ Preparation failed")
        return False

    # Step 6: Verify
    if not verify_update():
        print("\n⚠️  Verification incomplete")
        return False

    # Success!
    print("\n" + "=" * 70)
    print("✅ SUCCESS - Agent prompt updated!")
    print("=" * 70)
    print(f"\nNext steps:")
    print(f"  1. Wait 1-2 minutes for changes to fully propagate")
    print(f"  2. Run the test: python test_agent_optimization_v2.py")
    print(f"  3. Check results in S3 and compare to agent's claims")
    print("\n" + "=" * 70)

    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
# Day 1 Setup Guide - CFD Optimization Agent

## Overview
Today we're building the foundation: Lambda functions, tool schemas, and Bedrock Agent configuration.

## Prerequisites
- ✅ AWS Account with access to:
  - Lambda
  - Bedrock (with Claude Sonnet 4 access)
  - IAM
  - CloudFormation
- ✅ AWS CLI configured (`aws configure`)
- ✅ Python 3.12+
- ✅ Node.js 18+ (for CDK)

---

## Step 1: Environment Setup

### 1.1 Install Dependencies
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install CDK globally
npm install -g aws-cdk

# Install CDK Python dependencies
cd infra/cdk
pip install -r requirements.txt
cd ../..
```

### 1.2 Initialize CSV Storage
```bash
# Create CSV files with headers
python data/initialize_csvs.py
```

You should see:
```
✓ Created design_history.csv
✓ Created results.csv
```

---

## Step 2: Deploy Lambda Functions

### 2.1 Bootstrap CDK (First Time Only)
```bash
cd infra/cdk
cdk bootstrap
```

### 2.2 Deploy Infrastructure Stack
```bash
# Synthesize CloudFormation template
cdk synth

# Deploy stack
cdk deploy
```

When prompted "Do you wish to deploy these changes? (y/n)", type `y`.

This will create:
- ✅ 3 Lambda functions (generate_geometry, run_cfd, get_next_candidates)
- ✅ IAM roles for Lambda and Bedrock Agent
- ✅ CloudWatch Log Groups

**Save the outputs!** You'll need the Lambda ARNs and Agent Role ARN.

---

## Step 3: Test Lambda Functions Locally

Before creating the Bedrock Agent, verify each Lambda works:

### 3.1 Test Generate Geometry
```bash
cd lambdas/generate_geometry
python handler.py
```

Expected output:
```json
{
  "statusCode": 200,
  "body": "{\"geometry_id\": \"NACA4412_a2.0\", \"valid\": true, ...}"
}
```

### 3.2 Test Run CFD
```bash
cd ../run_cfd
python handler.py
```

Expected output:
```json
{
  "statusCode": 200,
  "body": "{\"Cl\": 0.3124, \"Cd\": 0.01421, ...}"
}
```

### 3.3 Test Get Next Candidates
```bash
cd ../get_next_candidates
python handler.py
```

Expected output:
```json
{
  "statusCode": 200,
  "body": "{\"candidates\": [...], \"strategy\": \"explore\", ...}"
}
```

---

## Step 4: Create Bedrock Agent

### 4.1 Run Setup Script
```bash
cd infra
python setup_bedrock_agent.py
```

This script will:
1. Read CDK outputs (Lambda ARNs, IAM role)
2. Create Bedrock Agent with Claude Sonnet 4
3. Load system prompt from `agent/prompts/system_prompt.txt`
4. Register action group with tool schemas
5. Create production alias
6. Save config to `agent/agent_config.json`

**This may take 2-3 minutes** while the agent is prepared.

### 4.2 Verify Agent Creation
```bash
# Check agent exists
aws bedrock-agent list-agents

# Get agent details (use agent_id from config)
aws bedrock-agent get-agent --agent-id <AGENT_ID>
```

---

## Step 5: Test Agent Invocation

### 5.1 Simple Test via AWS CLI
```bash
# Read agent config
cat agent/agent_config.json

# Test basic invocation
aws bedrock-agent-runtime invoke-agent \
  --agent-id <AGENT_ID> \
  --agent-alias-id <ALIAS_ID> \
  --session-id test-session-1 \
  --input-text "Hello, can you explain your optimization workflow?" \
  response.txt

# View response
cat response.txt
```

### 5.2 Test Tool Recognition
Create a simple Python test:

```python
# test_agent.py
import boto3
import json

# Load config
with open('agent/agent_config.json', 'r') as f:
    config = json.load(f)

bedrock_runtime = boto3.client('bedrock-agent-runtime')

response = bedrock_runtime.invoke_agent(
    agentId=config['agent_id'],
    agentAliasId=config['alias_id'],
    sessionId='test-session-2',
    inputText='What tools do you have available?'
)

# Parse streaming response
for event in response['completion']:
    if 'chunk' in event:
        chunk = event['chunk']
        if 'bytes' in chunk:
            print(chunk['bytes'].decode('utf-8'), end='')
```

Run it:
```bash
python test_agent.py
```

Expected agent response should mention:
- generate_geometry
- run_cfd  
- get_next_candidates

---

## Day 1 Success Criteria

You've completed Day 1 if:

✅ **Lambda Functions**
- All 3 Lambda functions deployed
- Each Lambda runs locally without errors
- Functions return expected JSON structure

✅ **Tool Schemas**
- OpenAPI schema created (`agent/schemas/tool_schemas.json`)
- Schema validates (JSON is well-formed)
- All parameters and responses documented

✅ **Bedrock Agent**
- Agent created with Claude Sonnet 4
- System prompt loaded successfully
- Action group registered with 3 tools
- Agent recognizes all tools when asked

✅ **Basic Invocation**
- Agent responds to simple prompts
- Agent can describe its tools
- No errors in CloudWatch logs

---

## Troubleshooting

### Issue: CDK Deploy Fails
**Error:** "Unable to resolve AWS account"
**Solution:** 
```bash
aws configure list  # Verify credentials
aws sts get-caller-identity  # Test access
```

### Issue: Bedrock Agent Creation Fails
**Error:** "AccessDeniedException"
**Solution:** Request Bedrock model access in AWS Console:
1. Go to Bedrock Console
2. Navigate to Model Access
3. Request access to "Anthropic Claude Sonnet 4"
4. Wait for approval (usually instant)

### Issue: Lambda Import Error
**Error:** "No module named 'X'"
**Solution:** Each Lambda needs its own dependencies:
```bash
cd lambdas/generate_geometry
pip install -t . <module_name>
```

For mock implementations, we only need standard library.

### Issue: Agent Doesn't Recognize Tools
**Solution:** 
1. Check OpenAPI schema is valid JSON
2. Verify action group was created: `aws bedrock-agent list-agent-action-groups --agent-id <ID>`
3. Re-prepare agent: `aws bedrock-agent prepare-agent --agent-id <ID>`

---

## What's Next? (Day 2)

Tomorrow we'll:
1. Implement realistic mock data in Lambda functions
2. Add CSV storage integration
3. Test complete generate → simulate → analyze workflow
4. Verify data persistence

---

## Quick Reference

### Key Files Created Today
```
lambdas/
├── generate_geometry/handler.py   # Geometry generation
├── run_cfd/handler.py             # CFD simulation  
├── get_next_candidates/handler.py # Optimization strategy
└── shared/storage.py              # CSV adapter

agent/
├── prompts/system_prompt.txt      # Agent instructions
├── schemas/tool_schemas.json      # OpenAPI definitions
└── agent_config.json              # Agent IDs (created by setup)

infra/
├── cdk/stacks/agent_stack.py      # Infrastructure code
└── setup_bedrock_agent.py         # Agent creation script

data/
├── design_history.csv             # Design evaluations
└── results.csv                    # Iteration summaries
```

### Useful Commands
```bash
# View Lambda logs
aws logs tail /aws/lambda/cfd-generate-geometry --follow

# Invoke Lambda directly
aws lambda invoke --function-name cfd-generate-geometry \
  --payload '{"parameters": {"thickness": 0.12, ...}}' \
  response.json

# Check agent status
aws bedrock-agent get-agent --agent-id <ID>

# List agent sessions
aws bedrock-agent-runtime list-sessions --agent-id <ID> --agent-alias-id <ALIAS>
```

---

## Need Help?

**Common Questions:**

Q: Do I need Bedrock access?
A: Yes, specifically access to Anthropic Claude Sonnet 4. Request it in the AWS Console under Bedrock → Model Access.

Q: Can I use a different AWS region?
A: Yes, but ensure Bedrock is available. Recommended regions: us-east-1, us-west-2.

Q: How much will this cost?
A: Day 1 should cost < $1:
- Lambda invocations: $0 (free tier)
- Bedrock tokens: ~$0.80 for testing
- CloudWatch: $0 (free tier)

Q: My agent times out
A: Increase Lambda timeout in `agent_stack.py` (line with `Duration.seconds(60)`)

---

**Day 1 Complete!** 🎉

You now have a working Bedrock Agent that can recognize and invoke three CFD optimization tools. Tomorrow we'll make these tools return realistic data and integrate CSV storage.
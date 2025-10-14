#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.storage_stack import StorageStack
from stacks.agent_stack import AgentStack
from stacks.orchestration_stack import OrchestrationStack
from stacks.step_functions_stack import StepFunctionsStack

app = cdk.App()

# 1. Storage first (foundation)
storage_stack = StorageStack(
    app,
    "CFDOptimizationStorageStack",
    description="S3 bucket for CFD optimization persistent data storage"
)

# 2. Agent stack with storage access
agent_stack = AgentStack(
    app,
    "CFDOptimizationAgentStack",
    storage_stack=storage_stack,
    description="CFD Optimization Agent - Lambda tools"
)

# 3. Orchestration stack with storage access
orchestration_stack = OrchestrationStack(
    app,
    "CFDOptimizationOrchestrationStack",
    storage_stack=storage_stack,
    description="CFD Optimization - Orchestration Lambdas"
)

# 4. Step Functions stack
step_functions_stack = StepFunctionsStack(
    app,
    "CFDOptimizationStepFunctionsStack",
    orchestration_stack=orchestration_stack,
    description="CFD Optimization - State machine"
)

app.synth()
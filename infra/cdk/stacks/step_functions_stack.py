# infra/cdk/stacks/step_functions_stack.py
"""
Step Functions Stack: Orchestrates CFD optimization workflow with S3 session management

State Machine Flow:
1. Initialize → Create S3 session, get sessionId
2. OptimizationLoop → Iterative optimization with Bedrock Agent
   - InvokeAgent → Agent generates candidates and runs CFD (with sessionId)
   - CheckConvergence → Read from S3 and decide if converged
   - ContinueLoop → Iterate or exit
3. GenerateReport → Create final summary from S3 data
"""

from aws_cdk import (
    Stack,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct
import json


class StepFunctionsStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            orchestration_stack,
            agent_stack,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Reference Lambda functions from orchestration stack
        initialize_fn = orchestration_stack.initialize_fn
        check_convergence_fn = orchestration_stack.check_convergence_fn
        generate_report_fn = orchestration_stack.generate_report_fn
        invoke_agent_fn = orchestration_stack.invoke_agent_fn

        # Reference Bedrock Agent
        # Reference Bedrock Agent from context
        agent_id = self.node.try_get_context("bedrock_agent_id")
        agent_alias_id = self.node.try_get_context("bedrock_agent_alias_id")

        if not agent_id:
            raise ValueError("bedrock_agent_id must be set in cdk.json context")

        # ==========================================
        # STATE MACHINE DEFINITION
        # ==========================================

        # Step 1: Initialize Optimization
        initialize_task = tasks.LambdaInvoke(
            self, "InitializeOptimization",
            lambda_function=initialize_fn,
            payload=sfn.TaskInput.from_object({
                "objective": "minimize_cd",
                "cl_min": 0.30,
                "reynolds": 500000,
                "max_iter": 8
            }),
            result_selector={
                "sessionId.$": "$.Payload.sessionId",
                "s3_enabled.$": "$.Payload.s3_enabled",
                "max_iter.$": "$.Payload.max_iter",
                "cl_min.$": "$.Payload.cl_min",
                "reynolds.$": "$.Payload.reynolds"
            },
            result_path="$.init"
        )

        # Step 2: Set Initial Iteration Counter
        set_iteration = sfn.Pass(
            self, "SetInitialIteration",
            parameters={
                "sessionId.$": "$.init.sessionId",
                "s3_enabled.$": "$.init.s3_enabled",
                "max_iter.$": "$.init.max_iter",
                "cl_min.$": "$.init.cl_min",
                "reynolds.$": "$.init.reynolds",
                "iteration": 0
            }
        )

        # Step 3: Invoke Bedrock Agent
        # The agent will call run_cfd and get_next_candidates with sessionId
        invoke_agent_task = tasks.LambdaInvoke(
            self, "InvokeBedrockAgent",
            lambda_function=invoke_agent_fn,
            payload=sfn.TaskInput.from_object({
                "agentId": agent_id,
                "agentAliasId": agent_alias_id,
                "sessionId.$": "$.sessionId",
                "iteration.$": "$.iteration",
                "inputText.$": sfn.JsonPath.format(
                    "Run CFD optimization iteration {} for session {}. " +
                    "CRITICAL: Use session_id='{}' in ALL tool calls (run_cfd, get_next_candidates). " +
                    "Generate 3 candidate designs, evaluate them, and propose the next iteration.",
                    sfn.JsonPath.string_at("$.iteration"),
                    sfn.JsonPath.string_at("$.sessionId"),
                    sfn.JsonPath.string_at("$.sessionId")
                )
            }),
            result_selector={
                "completion.$": "$.Payload.completion",
                "message.$": "$.Payload.message"
            },
            result_path="$.agentResult"
        )

        # Step 4: Check Convergence
        check_convergence_task = tasks.LambdaInvoke(
            self, "CheckConvergence",
            lambda_function=check_convergence_fn,
            payload=sfn.TaskInput.from_object({
                "sessionId.$": "$.sessionId",
                "iteration.$": "$.iteration",
                "max_iter.$": "$.max_iter",
                "cl_min.$": "$.cl_min"
            }),
            result_selector={
                "converged.$": "$.Payload.converged",
                "reason.$": "$.Payload.reason",
                "iteration.$": "$.Payload.iteration",
                "best_cd.$": "$.Payload.best_cd",
                "improvement_pct.$": "$.Payload.improvement_pct"
            },
            result_path="$.convergence"
        )

        # Step 5: Increment Iteration Counter
        increment_iteration = sfn.Pass(
            self, "IncrementIteration",
            parameters={
                "sessionId.$": "$.sessionId",
                "s3_enabled.$": "$.s3_enabled",
                "max_iter.$": "$.max_iter",
                "cl_min.$": "$.cl_min",
                "reynolds.$": "$.reynolds",
                "iteration.$": "States.MathAdd($.iteration, 1)",
                "convergence.$": "$.convergence"
            }
        )

        # Step 6: Converged Choice
        has_converged = sfn.Choice(self, "HasConverged")

        continue_loop = has_converged.when(
            sfn.Condition.boolean_equals("$.convergence.converged", False),
            increment_iteration
        )

        # Step 7: Generate Final Report
        generate_report_task = tasks.LambdaInvoke(
            self, "GenerateFinalReport",
            lambda_function=generate_report_fn,
            payload=sfn.TaskInput.from_object({
                "sessionId.$": "$.sessionId",
                "reason.$": "$.convergence.reason",
                "cl_min.$": "$.cl_min"
            }),
            result_selector={
                "report.$": "$.Payload"
            },
            result_path="$.finalReport"
        )

        # Step 8: Success State
        optimization_complete = sfn.Succeed(
            self, "OptimizationComplete",
            comment="CFD optimization completed successfully"
        )

        # ==========================================
        # CHAIN STATES TOGETHER
        # ==========================================

        # Define the workflow
        definition = (
            initialize_task
            .next(set_iteration)
            .next(invoke_agent_task)
            .next(check_convergence_task)
            .next(has_converged)
        )

        # Loop back or finish
        increment_iteration.next(invoke_agent_task)
        has_converged.otherwise(generate_report_task)
        generate_report_task.next(optimization_complete)

        # ==========================================
        # CREATE STATE MACHINE
        # ==========================================

        # CloudWatch log group for execution history
        log_group = logs.LogGroup(
            self, "StateMachineLogGroup",
            log_group_name="/aws/stepfunctions/cfd-optimization",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create the state machine
        state_machine = sfn.StateMachine(
            self, "CFDOptimizationWorkflow",
            state_machine_name="CFDOptimizationWorkflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(2),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True
            )
        )

        # Grant permissions to invoke Lambdas
        initialize_fn.grant_invoke(state_machine)
        check_convergence_fn.grant_invoke(state_machine)
        generate_report_fn.grant_invoke(state_machine)
        invoke_agent_fn.grant_invoke(state_machine)

        # ==========================================
        # OUTPUTS
        # ==========================================

        CfnOutput(
            self, "StateMachineArn",
            value=state_machine.state_machine_arn,
            description="CFD Optimization State Machine ARN",
            export_name="CFDOptimizationStateMachineArn"
        )

        CfnOutput(
            self, "StateMachineName",
            value=state_machine.state_machine_name,
            description="CFD Optimization State Machine Name"
        )

        # Store reference for other stacks
        self.state_machine = state_machine
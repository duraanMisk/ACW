"""
CDK Stack: CFD Optimization Agent Infrastructure
Sets up Lambda functions, IAM roles, and Bedrock Agent
"""
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct
import json
from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from .storage_stack import StorageStack


class AgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str,
                 storage_stack: Optional['StorageStack'] = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ==========================================
        # IAM ROLES
        # ==========================================

        # Lambda execution role
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Bedrock Agent execution role
        agent_role = iam.Role(
            self, "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Execution role for CFD Optimization Bedrock Agent"
        )

        # Grant agent permission to invoke Lambda functions (will add after creating them)

        # ==========================================
        # LAMBDA FUNCTIONS
        # ==========================================

        # Common Lambda configuration
        lambda_config = {
            "runtime": lambda_.Runtime.PYTHON_3_12,
            "timeout": Duration.seconds(60),
            "memory_size": 512,
            "role": lambda_role,
            "log_retention": logs.RetentionDays.ONE_WEEK,
        }

        # Lambda 1: Generate Geometry
        generate_geometry_fn = lambda_.Function(
            self, "GenerateGeometryFunction",
            function_name="cfd-generate-geometry",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/generate_geometry"),
            description="Generate and validate airfoil geometry from NACA parameters",
            **lambda_config
        )

        # Lambda 2: Run CFD (longer timeout for simulation)
        run_cfd_fn = lambda_.Function(
            self, "RunCFDFunction",
            function_name="cfd-run-cfd",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/run_cfd"),
            description="Run CFD simulation and return aerodynamic coefficients",
            runtime=lambda_.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(120),  # CFD may take longer than default
            memory_size=512,
            role=lambda_role,
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Lambda 3: Get Next Candidates
        get_candidates_fn = lambda_.Function(
            self, "GetNextCandidatesFunction",
            function_name="cfd-get-next-candidates",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/get_next_candidates"),
            description="Propose next optimization candidates using trust-region strategy",
            **lambda_config
        )

        # Grant Bedrock Agent permission to invoke all Lambda functions
        generate_geometry_fn.grant_invoke(agent_role)
        generate_geometry_fn.add_permission(
            "BedrockAgentInvokeGeometry",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account
        )

        run_cfd_fn.grant_invoke(agent_role)
        run_cfd_fn.add_permission(
            "BedrockAgentInvokeCFD",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account
        )

        get_candidates_fn.grant_invoke(agent_role)
        get_candidates_fn.add_permission(
            "BedrockAgentInvokeCandidates",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account
        )

        # ==========================================
        # BEDROCK AGENT
        # ==========================================

        # Note: Bedrock Agent cannot be fully created via CDK yet
        # We'll use AWS CLI or Console to complete this
        # This stack sets up all the prerequisites

        # Action Group Lambda ARNs (to be used in agent configuration)
        self.action_group_lambdas = {
            "generate_geometry": generate_geometry_fn.function_arn,
            "run_cfd": run_cfd_fn.function_arn,
            "get_next_candidates": get_candidates_fn.function_arn,
        }

        if storage_stack:
            print("Granting S3 and SSM access to tool Lambdas...")

            # Tool Lambdas need S3 read/write
            tool_lambdas = [
                generate_geometry_fn,
                run_cfd_fn,
                get_candidates_fn
            ]

            for lambda_fn in tool_lambdas:
                # S3 access
                storage_stack.bucket.grant_read_write(lambda_fn)

                # SSM read access (to get session_id from execution_id)
                lambda_fn.add_to_role_policy(iam.PolicyStatement(
                    actions=["ssm:GetParameter"],
                    resources=[
                        f"arn:aws:ssm:{self.region}:{self.account}:parameter/cfd-optimization/sessions/*"
                    ]
                ))

        self.generate_geometry_fn = generate_geometry_fn
        self.run_cfd_fn = run_cfd_fn
        self.get_candidates_fn = get_candidates_fn

        # ==========================================
        # OUTPUTS
        # ==========================================

        CfnOutput(
            self, "GenerateGeometryFunctionArn",
            value=generate_geometry_fn.function_arn,
            description="ARN of generate_geometry Lambda function"
        )

        CfnOutput(
            self, "RunCFDFunctionArn",
            value=run_cfd_fn.function_arn,
            description="ARN of run_cfd Lambda function"
        )

        CfnOutput(
            self, "GetNextCandidatesFunctionArn",
            value=get_candidates_fn.function_arn,
            description="ARN of get_next_candidates Lambda function"
        )

        CfnOutput(
            self, "AgentRoleArn",
            value=agent_role.role_arn,
            description="ARN of Bedrock Agent execution role"
        )

        CfnOutput(
            self, "BedrockAgentSetupInstructions",
            value="Use AWS Console or CLI to create Bedrock Agent with the Lambda ARNs and Role ARN above",
            description="Next steps for Bedrock Agent setup"
        )






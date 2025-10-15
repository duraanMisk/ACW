# infra/cdk/stacks/orchestration_stack.py
"""
Orchestration Stack: Lambda functions for Step Functions workflow with shared layer

Creates:
- Lambda Layer with shared S3 modules (session_manager, s3_storage)
- 4 orchestration Lambda functions with the layer attached
"""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct


class OrchestrationStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Reference the S3 bucket from storage stack
        bucket = storage_stack.bucket

        # ==========================================
        # LAMBDA LAYER - Shared Modules
        # ==========================================
        print("Creating Lambda Layer for shared modules...")

        shared_layer = lambda_.LayerVersion(
            self, "SharedModulesLayer",
            code=lambda_.Code.from_asset("../../lambdas/shared"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared S3 storage and session management modules",
            layer_version_name="cfd-optimization-shared-modules"
        )

        # ==========================================
        # IAM ROLE
        # ==========================================
        lambda_role = iam.Role(
            self, "OrchestrationLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for CFD optimization orchestration functions",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        print("Granting S3 and SSM access to orchestration Lambdas...")

        # S3 permissions for optimization data storage
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            resources=[
                bucket.bucket_arn,
                f"{bucket.bucket_arn}/*"
            ]
        ))

        # SSM permissions for config
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ssm:GetParameter",
                "ssm:GetParameters"
            ],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter/cfd-optimization/*"
            ]
        ))

        # ==========================================
        # LAMBDA FUNCTIONS
        # ==========================================

        # Common config
        lambda_config = {
            "runtime": lambda_.Runtime.PYTHON_3_12,
            "role": lambda_role,
            "timeout": Duration.seconds(30),
            "memory_size": 256,
            "log_retention": logs.RetentionDays.ONE_WEEK,
            "layers": [shared_layer],
            "environment": {
                "LOG_LEVEL": "INFO",
                "S3_BUCKET": bucket.bucket_name
                # AWS_REGION is automatically provided by Lambda - don't set it
            }
        }

        # 1. Initialize Optimization Function
        initialize_fn = lambda_.Function(
            self, "InitializeOptimization",
            function_name="cfd-initialize-optimization",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/initialize_optimization"),
            description="Initialize CFD optimization run - create S3 session",
            **lambda_config
        )

        # 2. Check Convergence Function
        check_convergence_fn = lambda_.Function(
            self, "CheckConvergence",
            function_name="cfd-check-convergence",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/check_convergence"),
            description="Check optimization convergence criteria",
            **lambda_config
        )

        # 3. Generate Report Function
        generate_report_fn = lambda_.Function(
            self, "GenerateReport",
            function_name="cfd-generate-report",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/generate_report"),
            description="Generate optimization summary report",
            **lambda_config
        )

        # 4. Invoke Bedrock Agent Function
        invoke_agent_fn = lambda_.Function(
            self, "InvokeBedrockAgent",
            function_name="cfd-invoke-bedrock-agent",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/invoke_bedrock_agent"),
            timeout=Duration.seconds(120),
            description="Invoke Bedrock Agent wrapper for Step Functions",
            runtime=lambda_.Runtime.PYTHON_3_12,
            role=lambda_role,
            memory_size=256,
            log_retention=logs.RetentionDays.ONE_WEEK,
            layers=[shared_layer],
            environment={
                "LOG_LEVEL": "INFO",
                "S3_BUCKET": bucket.bucket_name
                # AWS_REGION is automatically provided by Lambda
            }
        )

        # Grant Bedrock permissions to invoke_agent_fn
        invoke_agent_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeAgent",
                "bedrock:InvokeModel"
            ],
            resources=["*"]
        ))

        orchestration_lambdas = [
            initialize_fn,
            check_convergence_fn,
            generate_report_fn,
            invoke_agent_fn  # Might not need S3, but doesn't hurt
        ]

        for lambda_fn in orchestration_lambdas:
            storage_stack.bucket.grant_read_write(lambda_fn)

        print("✓ Granted S3 permissions to orchestration Lambdas")

        # ==========================================
        # OUTPUTS
        # ==========================================
        CfnOutput(
            self, "SharedLayerArn",
            value=shared_layer.layer_version_arn,
            description="Shared modules Lambda Layer ARN"
        )

        CfnOutput(
            self, "InitializeFunctionArn",
            value=initialize_fn.function_arn,
            description="Initialize Optimization Lambda ARN"
        )

        CfnOutput(
            self, "CheckConvergenceFunctionArn",
            value=check_convergence_fn.function_arn,
            description="Check Convergence Lambda ARN"
        )

        CfnOutput(
            self, "GenerateReportFunctionArn",
            value=generate_report_fn.function_arn,
            description="Generate Report Lambda ARN"
        )

        CfnOutput(
            self, "InvokeAgentFunctionArn",
            value=invoke_agent_fn.function_arn,
            description="Invoke Bedrock Agent Lambda ARN"
        )

        CfnOutput(
            self, "LambdaRoleArn",
            value=lambda_role.role_arn,
            description="Lambda Execution Role ARN"
        )

        # Store references for Step Functions stack
        self.initialize_fn = initialize_fn
        self.check_convergence_fn = check_convergence_fn
        self.generate_report_fn = generate_report_fn
        self.invoke_agent_fn = invoke_agent_fn
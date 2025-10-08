from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    CfnOutput,
)
from constructs import Construct


class CFDOptimizationAgentStack(Stack):
    """Stack for CFD optimization tool Lambda functions."""

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            results_bucket: s3.Bucket,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.results_bucket = results_bucket

        # Create IAM role for Lambda functions
        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Grant S3 permissions
        results_bucket.grant_read_write(lambda_role)

        # Common Lambda configuration
        common_config = {
            "runtime": _lambda.Runtime.PYTHON_3_12,
            "timeout": Duration.seconds(30),
            "memory_size": 256,
            "role": lambda_role,
            "environment": {
                "RESULTS_BUCKET": results_bucket.bucket_name,
                # SESSION_ID will be passed at runtime by Step Functions
            },
            "log_retention": logs.RetentionDays.ONE_WEEK,
        }

        # Lambda 1: Generate Geometry
        self.generate_geometry = _lambda.Function(
            self,
            "GenerateGeometry",
            function_name="cfd-generate-geometry",
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("../../lambdas/generate_geometry"),
            description="Generate NACA airfoil geometry and validate mesh quality",
            **common_config,
        )

        # Lambda 2: Run CFD (needs longer timeout than others)
        run_cfd_config = {**common_config}
        run_cfd_config["timeout"] = Duration.seconds(60)  # CFD might take longer

        self.run_cfd = _lambda.Function(
            self,
            "RunCFD",
            function_name="cfd-run-cfd",
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("../../lambdas/run_cfd"),
            description="Run CFD simulation and return aerodynamic coefficients",
            **run_cfd_config,
        )

        # Lambda 3: Get Next Candidates
        self.get_next_candidates = _lambda.Function(
            self,
            "GetNextCandidates",
            function_name="cfd-get-next-candidates",
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("../../lambdas/get_next_candidates"),
            description="Analyze design history and propose next optimization candidates",
            **common_config,
        )

        # Create Bedrock Agent execution role
        bedrock_agent_role = iam.Role(
            self,
            "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Role for Bedrock Agent to invoke Lambda functions",
        )

        # Grant Bedrock Agent permission to invoke model
        bedrock_agent_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
                ],
            )
        )

        # Grant Bedrock Agent permission to invoke Lambda functions
        for func in [self.generate_geometry, self.run_cfd, self.get_next_candidates]:
            func.grant_invoke(bedrock_agent_role)

        # Outputs
        CfnOutput(
            self,
            "GenerateGeometryFunctionArn",
            value=self.generate_geometry.function_arn,
            export_name="CFDGenerateGeometryArn",
        )

        CfnOutput(
            self,
            "RunCFDFunctionArn",
            value=self.run_cfd.function_arn,
            export_name="CFDRunCFDArn",
        )

        CfnOutput(
            self,
            "GetNextCandidatesFunctionArn",
            value=self.get_next_candidates.function_arn,
            export_name="CFDGetNextCandidatesArn",
        )

        CfnOutput(
            self,
            "AgentRoleArn",
            value=bedrock_agent_role.role_arn,
            description="Use this role when creating Bedrock Agent",
        )

        CfnOutput(
            self,
            "BedrockAgentSetupInstructions",
            value="Use AWS Console or CLI to create Bedrock Agent with the Lambda ARNs and Role ARN above",
        )
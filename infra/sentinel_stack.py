"""Sentinel serverless stack: DynamoDB cache + Lambda API + HTTP API Gateway."""

from __future__ import annotations

import os

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-opus-5")


class SentinelStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Cache ----------------------------------------------------------
        table = dynamodb.Table(
            self,
            "AnalysisCache",
            table_name="SentinelAnalysisCache",
            partition_key=dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            # Native TTL sweep. The application still checks expiresAt on read,
            # because DynamoDB's deletion is eventual (up to ~48h) and a stale
            # verdict served in that window is exactly what we must avoid.
            time_to_live_attribute="expiresAt",
            removal_policy=RemovalPolicy.DESTROY,  # cache only; safe to drop
        )

        # --- API Lambda -----------------------------------------------------
        api_fn = lambda_.Function(
            self,
            "AnalyzeFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_handler.handler",
            code=lambda_.Code.from_asset(
                "../backend",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output "
                        "&& cp -au . /asset-output",
                    ],
                ),
            ),
            # Image download + multimodal inference is the slow part; the model
            # call alone can run tens of seconds at high effort.
            timeout=Duration.seconds(120),
            memory_size=1024,
            log_retention=logs.RetentionDays.ONE_WEEK,
            # AWS_REGION is reserved — the Lambda runtime sets it automatically,
            # and app/config.py reads it from there.
            environment={
                "MOCK_AWS": "false",
                "DDB_TABLE_NAME": table.table_name,
                "BEDROCK_MODEL_ID": MODEL_ID,
                "LOG_LEVEL": "INFO",
            },
        )

        table.grant_read_write_data(api_fn)

        # Bedrock model invocation. Scoped to the one model this stack uses
        # rather than a blanket wildcard.
        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/{MODEL_ID}*",
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/*",
                ],
            )
        )

        # --- HTTP API -------------------------------------------------------
        http_api = apigw.HttpApi(
            self,
            "SentinelApi",
            api_name="sentinel-api",
            cors_preflight=apigw.CorsPreflightOptions(
                # The extension's chrome-extension:// origin is only known once
                # the extension is packed, so this stays open at the gateway and
                # is narrowed in the app's CORS middleware.
                allow_origins=["*"],
                allow_methods=[apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.GET],
                allow_headers=["content-type"],
                max_age=Duration.hours(1),
            ),
        )

        http_api.add_routes(
            path="/{proxy+}",
            methods=[apigw.HttpMethod.ANY],
            integration=integrations.HttpLambdaIntegration("ApiIntegration", api_fn),
        )

        CfnOutput(self, "ApiUrl", value=http_api.api_endpoint)
        CfnOutput(self, "TableName", value=table.table_name)

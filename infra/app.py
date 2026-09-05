#!/usr/bin/env python3
"""CDK entrypoint.

    cd infra
    pip install -r requirements.txt
    cdk deploy

Note: the `cdk` CLI is a Node application even for a Python CDK app, so
deploying needs Node installed. Everything else in this repo does not.
"""

import os

import aws_cdk as cdk

from sentinel_stack import SentinelStack

app = cdk.App()

SentinelStack(
    app,
    "SentinelStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
    ),
    description="Sentinel: e-commerce scam prevention API (Bedrock + DynamoDB)",
)

app.synth()

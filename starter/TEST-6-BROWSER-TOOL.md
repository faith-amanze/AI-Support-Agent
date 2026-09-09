# Test 6 — Browser Tool

## Status: Blocked (confirmed sandbox permission restriction, not a code defect)

## What was tested
Prompted the agent to navigate to udacity.com using the browser tool and
retrieve the page title.

## Result
The agent invoked the browser tool correctly (visible in logs as
'Tool #1: browser', 'Tool #2: browser' -- the second call was the model's
own self-correction after an invalid session_name with an underscore,
which is expected Pydantic validation behavior, not a bug). The tool call
itself failed with an AWS permissions error.

## Root cause (confirmed via CloudWatch DEBUG logs)
\\\
AccessDeniedException: User: arn:aws:sts::071203467605:assumed-role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-aa96c3a063/...
is not authorized to perform: bedrock-agentcore:StartBrowserSession on resource:
arn:aws:bedrock-agentcore:us-east-1:aws:browser/aws.browser.v1
because no identity-based policy allows the bedrock-agentcore:StartBrowserSession action
\\\

## Why this is not a code issue
The agent's browser tool wiring, session initialization, and MCP/Strands
integration are all correctly implemented. The failure occurs entirely at
the AWS IAM layer: the agent's runtime execution role
(AmazonBedrockAgentCoreSDKRuntime-us-east-1-aa96c3a063) lacks the
bedrock-agentcore:StartBrowserSession permission, and this sandbox account
does not permit self-service IAM role modification for this class of
permission.

This is consistent with three other confirmed, unrelated sandbox
restrictions encountered during this project (aoss:CreateSecurityPolicy,
iam:GetRole, cloudtrail:LookupEvents), all fixed at the account level with
no self-service remediation path available. See REFLECTION.md for further
discussion.

"""
Customer Support AI Agent -- Starter Code
==========================================
Your task is to complete this file by implementing all sections marked
with # TODO comments.

Reference the step-by-step solution files and INSTRUCTIONS.md for guidance.
Do NOT copy the solution directly -- work through each section yourself.

Run locally (after filling in config values):
  uv run main.py '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'

Deploy to AgentCore:
  agentcore deploy

Invoke deployed agent:
  agentcore invoke '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'
"""

# -- Imports -------------------------------------------------------------------
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamable_http_client
import argparse, json
import os, asyncio, boto3
from strands.hooks import (
    HookProvider, AfterInvocationEvent, HookRegistry, MessageAddedEvent,
)
import logging
import uuid
from typing import Dict
from bedrock_agentcore.tools.code_interpreter_client import code_session
from strands_tools.browser import AgentCoreBrowser


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("CSAI_Agent")

app = BedrockAgentCoreApp()

os.environ["BYPASS_TOOL_CONSENT"] = "true"

GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://customersupportgateway-c3kphwcoil.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp")
KB_ID       = os.environ.get("KB_ID", "<kbid>")
REGION      = os.environ.get("REGION", "us-east-1")
MEMORY_ID   = os.environ.get("MEMORY_ID", "CustomerSupportMemory-rNlj1Z5aev")

model_id = "global.amazon.nova-2-lite-v1:0"

model = BedrockModel(model_id=model_id)

memory_client = MemoryClient(region_name=REGION)

_bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


def get_namespaces(mem_client: MemoryClient, memory_id: str) -> Dict:
    """Return a dict mapping strategy type to namespace template string."""
    strategies = mem_client.get_memory_strategies(memory_id)
    return {strategy["type"]: strategy["namespaces"][0] for strategy in strategies}


class MemoryHook(HookProvider):
    """Long-term memory hook for the customer support agent."""

    def __init__(
        self,
        actor_id: str,
        session_id: str,
        memory_client: MemoryClient,
        memory_id: str,
    ):
        self.actor_id = actor_id
        self.session_id = session_id
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.namespaces = get_namespaces(memory_client, memory_id)

    def retrieve_customer_context(self, event: MessageAddedEvent):
        """Retrieve relevant memories and prepend them to the user message."""
        messages = event.agent.messages
        if not messages:
            return

        last_message = messages[-1]

        if last_message.get("role") != "user":
            return

        content = last_message.get("content") or []
        if not content or "text" not in content[0]:
            return

        user_query = content[0]["text"]

        memory_snippets = []
        for strategy_type, namespace_template in self.namespaces.items():
            try:
                namespace = namespace_template.format(actorId=self.actor_id)
                memories = self.memory_client.retrieve_memories(
                    memory_id=self.memory_id,
                    namespace=namespace,
                    query=user_query,
                    top_k=5,
                )
            except Exception as e:
                logger.warning(f"Memory retrieval failed for {strategy_type}: {e}")
                continue

            for memory in memories:
                text = memory.get("content", {}).get("text", "")
                if text:
                    memory_snippets.append(f"[{strategy_type}] {text}")

        if memory_snippets:
            context_block = "\n".join(memory_snippets)
            content[0]["text"] = f"Customer Context:\n{context_block}\n\n{user_query}"

    def save_support_interaction(self, event: AfterInvocationEvent):
        """Save the completed turn to memory after the agent responds."""
        messages = event.agent.messages

        customer_query = None
        agent_response = None

        for message in reversed(messages):
            role = message.get("role")
            content = message.get("content") or []
            if not content or "text" not in content[0]:
                continue

            if role == "assistant" and agent_response is None:
                agent_response = content[0]["text"]
            elif role == "user" and customer_query is None:
                customer_query = content[0]["text"]

            if customer_query and agent_response:
                break

        if not (customer_query and agent_response):
            return

        try:
            self.memory_client.create_event(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                messages=[(customer_query, "USER"), (agent_response, "ASSISTANT")],
            )
        except Exception as e:
            logger.warning(f"Failed to save support interaction to memory: {e}")

    def register_hooks(self, registry: HookRegistry) -> None:
        """Register both memory callbacks."""
        registry.add_callback(MessageAddedEvent, self.retrieve_customer_context)
        registry.add_callback(AfterInvocationEvent, self.save_support_interaction)


@tool
def search_knowledge_base(query: str) -> str:
    """
    Search the Amazon product catalog and support knowledge base.
    Use this for product specifications, return policies, warranty
    information, loyalty program details, and order status definitions.

    Args:
        query: The question or topic to search for

    Returns:
        Relevant information retrieved from the knowledge base
    """
    if not KB_ID or KB_ID == "<kbid>":
        return "Knowledge base not configured."

    try:
        resp = _bedrock_runtime.retrieve(
            knowledgeBaseId=KB_ID,
            retrievalQuery={"text": query},
        )
    except Exception as e:
        logger.error(f"Knowledge base retrieve call failed: {e}")
        return f"Knowledge base search failed: {e}"

    results = resp.get("retrievalResults", [])
    if not results:
        return "No relevant information found in the knowledge base for that query."

    chunks = [
        r["content"]["text"]
        for r in results
        if r.get("content", {}).get("text")
    ]
    return "\n---\n".join(chunks)


@tool
def calculate_loyalty_discount(
    loyalty_points: int,
    tier: str,
    order_total: float,
    product_category: str = "standard",
) -> str:
    """
    Calculate the loyalty discount for a customer order using the
    AgentCore Code Interpreter. Runs exact arithmetic in a secure sandbox.

    Args:
        loyalty_points:   Customer's current points balance
        tier:             Customer tier -- Silver, Gold, or Platinum
        order_total:      Order total in USD
        product_category: standard, device, or fresh

    Returns:
        Full discount breakdown and final price
    """
    code = f"""
import json

earn_rates = {{"standard": 1, "device": 2, "fresh": 5}}
tier_rates = {{"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}}

loyalty_points = {loyalty_points}
tier = "{tier}"
order_total = {order_total}
product_category = "{product_category}"

POINT_VALUE = 0.01

max_points_by_value = int((order_total * 0.5) / POINT_VALUE)
points_cap = min(loyalty_points, max_points_by_value)
points_redeemed = (points_cap // 500) * 500
points_discount = points_redeemed * POINT_VALUE

subtotal_after_points = order_total - points_discount
tier_discount_rate = tier_rates.get(tier, 0.00)
tier_discount_amount = subtotal_after_points * tier_discount_rate

final_total = round(subtotal_after_points - tier_discount_amount, 2)
total_savings = round(order_total - final_total, 2)

points_earned = int(round(final_total * earn_rates.get(product_category, 1)))
remaining_points = loyalty_points - points_redeemed + points_earned

result = {{
    "order_total": order_total,
    "tier": tier,
    "points_redeemed": points_redeemed,
    "points_discount": round(points_discount, 2),
    "tier_discount_rate": tier_discount_rate,
    "tier_discount_amount": round(tier_discount_amount, 2),
    "final_total": final_total,
    "total_savings": total_savings,
    "points_earned": points_earned,
    "remaining_points": remaining_points,
}}

print(json.dumps(result))
"""

    try:
        with code_session(REGION) as code_client:
            response = code_client.invoke(
                "executeCode",
                {
                    "code": code,
                    "language": "python",
                    "clearContext": True,
                },
            )
            for event in response["stream"]:
                return json.dumps(event["result"])

    except Exception as e:
        logger.warning(f"Code Interpreter unavailable, using fallback calculation: {e}")
        tier_rates = {"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}
        tier_discount_rate = tier_rates.get(tier, 0.00)
        tier_discount_amount = round(order_total * tier_discount_rate, 2)
        final_total = round(order_total - tier_discount_amount, 2)

        fallback_result = {
            "order_total": order_total,
            "tier": tier,
            "tier_discount_rate": tier_discount_rate,
            "tier_discount_amount": tier_discount_amount,
            "final_total": final_total,
            "total_savings": tier_discount_amount,
            "note": "Fallback calculation used (Code Interpreter unavailable) -- "
                    "points redemption was not applied.",
        }
        return json.dumps(fallback_result)


@app.entrypoint
async def invoke(payload, context=None):
    """
    Main handler called by AgentCore for every incoming request.

    Expected payload keys:
      prompt      (str, required) -- the customer's message
      customer_id (str, optional) -- unique customer identifier
      session_id  (str, optional) -- session identifier; generated if absent
    """
    try:
        user_input = payload.get("prompt", "")
        actor_id = payload.get("customer_id", "anonymous")
        session_id = payload.get("session_id") or str(uuid.uuid4())

        memory_hook = MemoryHook(
            actor_id=actor_id,
            session_id=session_id,
            memory_client=memory_client,
            memory_id=MEMORY_ID,
        )

        agent_core_browser = AgentCoreBrowser(region=REGION)

        tools = [
            search_knowledge_base,
            calculate_loyalty_discount,
            agent_core_browser.browser,
        ]

        system_prompt = (
            "You are a helpful customer support assistant for an e-commerce "
            "platform. You can look up orders and customer profiles, process "
            "refunds and return labels, answer product/policy questions using "
            "the knowledge base, calculate exact loyalty discounts, and browse "
            "live web pages when needed. Always use your tools to get accurate, "
            "up-to-date information rather than guessing. Be concise, friendly, "
            "and precise with numbers, order IDs, and dates."
        )

        mcp_client = MCPClient(lambda: streamable_http_client(GATEWAY_URL))
        with mcp_client:
            gateway_tools = mcp_client.list_tools_sync()
            tools.extend(gateway_tools)

            agent = Agent(
                model=model,
                tools=tools,
                hooks=[memory_hook],
                system_prompt=system_prompt,
            )

            response = await agent.invoke_async(user_input)
            return response.message["content"][0]["text"]

    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        return (
            "I'm sorry, something went wrong while processing your request. "
            f"Details: {e}"
        )


def main():
    """Run one invocation from the command line for local testing."""
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=str)
    args = parser.parse_args()
    response = asyncio.run(invoke(json.loads(args.payload)))
    print(response)


if __name__ == "__main__":
    app.run()
    # Uncomment the line below and comment app.run() for local CLI testing:
    # main()  # Uncomment for local CLI testing instead



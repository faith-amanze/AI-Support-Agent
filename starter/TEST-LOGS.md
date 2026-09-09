# Test Conversation Logs

## Test 1 - Order Tracking (ORD-001, CUST-123)
Status: PASSED

Response:
Here are the details for order ORD-001 for customer CUST-123:
- Status: SHIPPED
- Items: Wireless Headphones Pro x1 ($89.99)
- Total: $89.99
- Tracking Number: TRK987654321
- Carrier: UPS
- Estimated Delivery: 2026-09-11

---

## Test 2 - Refund Processing (Kindle Paperwhite, ORD-002)
Status: PASSED

Response:
The refund has been successfully processed for Kindle Paperwhite order ORD-002.
- Refund ID: REF-Y56C88X4
- Status: APPROVED
- Refund Amount: $139.99
- Processing Time: 3-5 business days
- Date Processed: September 9, 2026

The agent also correctly recalled prior loyalty discount context from memory.

---

## Test 3 - Knowledge Base / RAG ("Platinum loyalty tier benefits")
Status: PASSED

Response:
Platinum tier (5,000+ points) benefits: free same-day shipping, 15% discount,
priority customer support. Retrieved from the Bedrock-managed Knowledge Base
(KB ID: Z15BUJFN54) after attaching an inline IAM policy granting
bedrock:Retrieve to the agent execution role.

---

## Test 4 - Long-Term Memory (two separate sessions)
Status: PASSED

Part 1 (session test4-session-one) established: "favorite product category
is fitness trackers." Part 2, 30+ seconds later in a separate session
(test4-session-two), correctly recalled this along with prior Gold tier,
points, and communication preference context, confirming cross-session
persistence via the custom MemoryHook.

---

## Test 5 - Loyalty Discount (Gold, 4250 pts, $150 order)
Status: PASSED

Response:
- Order Total: $150.00
- Points Redeemed: 4,000 ($40.00 discount)
- Gold Tier Discount: 10% ($11.00)
- Final Price: $99.00
- New Points Earned: 99
- Remaining Points: 349

Exact match to expected values, computed via AgentCore Code Interpreter.

---

## Test 6 - Browser Tool (navigate to udacity.com, get page title)
Status: PASSED

Response:
Page title of udacity.com: "Learn the Latest Tech Skills; Advance Your
Career | Udacity"

Initially failed with AccessDeniedException on
bedrock-agentcore:StartBrowserSession. Resolved by attaching a targeted
inline IAM policy granting browser session permissions to the agent
execution role. See REFLECTION.md for discussion.

# AtlasCare — KPI Framework
**Project:** AtlasCare — Agentic AI for Customer Contact  
**Client:** Acme Retail Co.  
**Version:** v1.0 | 31 May 2026


## Overview

KPIs are grouped into four layers. Each layer has one table covering all metrics for that group.

**Data sources:** `performance_logs` table · `cases` table · `Tracer.calls` (per-request trace) · FastAPI router metrics

<br>

## Layer 1 — Business KPIs
*Did AtlasCare deliver value to the business?*

| # | KPI | What It Measures | Formula | Target | Alert |
|---|---|---|---|---|---|
| B1 | **Deflection Rate** | % of chats fully resolved by AI without a human agent | `(non-escalated interactions / total) × 100` | ≥ 85% | < 75% → P2 |
| B2 | **API Cost per Interaction** | LLM token cost spent per resolved customer chat | `(total_tokens / 1000) × $0.0007 / total_interactions` | < $0.005 | > $15/day → email alert |
| B3 | **Cost Avoidance (₹/day)** | Money saved vs. routing the same volume to human agents | `deflected_interactions × avg_human_agent_cost` | Track vs. pre-launch baseline | Set baseline at go-live |
| B4 | **Journey Distribution** | Split of interaction types (order lookup, cancel, policy, etc.) | `COUNT per journey / total × 100` | No single journey > 60% | Monthly review |
| B5 | **Customer Satisfaction (CSAT)** | % of customers who rated the interaction positively | `positive_ratings / total_rated × 100` | ≥ 80% | < 70% → P2 |
| B6 | **First Contact Resolution (FCR)** | % of issues fully resolved in one session (no follow-up needed) | `sessions with no repeat contact in 48h / total_sessions × 100` | ≥ 80% | Daily review |


<br>

## Layer 2 — Quality KPIs
*Did AtlasCare give correct, accurate answers?*

| # | KPI | What It Measures | Formula | Target | Alert |
|---|---|---|---|---|---|
| Q1 | **Tool Call Success Rate** | % of tool executions (OMS, CRM, KB, Payments) that returned a valid result | `successful_tool_calls / total_tool_calls × 100` | ≥ 97% | < 90% → P1 |
| Q2 | **Hallucination Rate** | % of responses containing order/product details not in the actual data | Spot-check 5% of Order Lookup sessions; compare agent response vs. raw tool output | 0% | Any instance → P1 |
| Q3 | **Refund Threshold Compliance** | % of refund decisions that correctly applied the ₹25,000 auto-refund ceiling | `correct_threshold_decisions / total_refund_decisions × 100` | 100% | Any breach → P0 |
| Q4 | **Escalation Accuracy** | % of escalations that genuinely required a human (not false alarms) | `true_escalations / total_escalations × 100` (requires human review labels) | ≥ 95% | Weekly review |
| Q5 | **Multi-Step Completion Rate** | % of compound requests (J2) where all steps completed without partial failure | `J2_sessions with all tool_calls success / total_J2_sessions × 100` | ≥ 90% | < 80% → P2 |
| Q6 | **Memory Reuse Rate** | % of follow-up turns where agent correctly used conversation history instead of calling a tool again | Audit: count redundant tool calls in same-session follow-up turns | ≥ 95% | Weekly audit |


<br>

## Layer 3 — Safety KPIs
*Did AtlasCare stay within its guardrails?*

| # | KPI | What It Measures | Formula | Target | Alert |
|---|---|---|---|---|---|
| S1 | **Autonomous Refund Limit Breaches** | Number of times AI processed a refund above ₹25,000 without human approval | Count of auto-refunds where `amount > 25,000` | 0 — zero tolerance | Any occurrence → P0 (agent shutdown) |
| S2 | **Cross-Customer Data Leaks** | Number of times a customer received another customer's order or profile data | Automated check: `customer_id` in tool output vs. authenticated user's `customer_id` | 0 — zero tolerance | Any occurrence → P0 (privacy breach) |
| S3 | **Escalation Case Creation Rate** | % of escalations that correctly created a CRM case with a trace_id (audit trail completeness) | `cases_created / total_escalated_sessions × 100` | 100% | Any miss → P1 |
| S4 | **Duplicate Escalation Prevention** | % of repeat escalation attempts for the same order+item that were correctly blocked | `blocked_duplicates / total_duplicate_attempts × 100` | 100% | Any duplicate created → P1 |
| S5 | **Invalid Auth Rejection Rate** | % of requests with bad/expired/missing tokens that were correctly rejected | `401_or_403_responses / invalid_token_requests × 100` | 100% | > 5% of all requests returning 401 → P2 |
| S6 | **Rate Limit Enforcement** | % of sessions correctly throttled after exceeding 10 requests per minute | `throttled_requests / requests_over_limit × 100` | 100% | Monitor limiter error logs |
| S7 | **PII Exposure in Logs** | Instances of phone numbers, addresses, or card identifiers written to application logs in plaintext | Weekly automated log scan with regex patterns | 0 | Any detection → P1 |


<br>

## Layer 4 — Operational KPIs
*Is AtlasCare running reliably and efficiently?*

| # | KPI | What It Measures | Formula | Target | Alert |
|---|---|---|---|---|---|
| O1 | **Response Latency (p95)** | 95th-percentile end-to-end response time for `/query` | Measured from request receipt to full response delivery | J1 < 3,000 ms · All journeys < 8,000 ms | > 10,000 ms → P2 |
| O2 | **System Uptime** | % of time the service is healthy and responding | `successful /health checks / total checks × 100` | ≥ 99.5% per month | 2 consecutive failures → P1 |
| O3 | **Timeout Rate** | % of requests hitting the 15-second hard timeout (indicates runaway agent or slow LLM) | `timeout_responses / total_requests × 100` | < 0.5% | > 2% → P1 |
| O4 | **Unhandled Error Rate** | % of requests returning the generic fallback error message (something broke unexpectedly) | `generic_error_responses / total_requests × 100` | < 0.1% | > 1% → P1 |
| O5 | **Open Escalation Queue Depth** | Number of CRM cases currently open and awaiting a human specialist | `COUNT(*) FROM cases WHERE status = 'open'` | < 50 cases at any time | > 100 → P2 |
| O6 | **Escalation SLA Compliance** | % of open cases resolved within the 24-hour specialist response SLA | `cases resolved within 24h / total_resolved × 100` | ≥ 95% | Alert at 20-hour mark |
| O7 | **Token Efficiency** | Average LLM tokens consumed per interaction (guards against prompt bloat or agent loops) | `SUM(tokens_used) / COUNT(interactions)` | < 12,000 tokens avg | > 20,000 avg → review agent loop |




---

*AtlasCare Engineering Team · Acme Retail Co.*

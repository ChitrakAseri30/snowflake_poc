# AtlasCare - Architecture Document
**Version:** 1.0 | **Scope:** Planning Approach, Tool Strategy, Guardrails and Observability

---

## 1. Planning Approach

AtlasCare utilizes a zero-trust, dual-track orchestration architecture. It combines a secure API gateway with an intelligent intent classifier that seamlessly bifurcates traffic between low-latency deterministic handlers and a sophisticated LangGraph reasoning loop for complex enterprise workflows.


![High Level Diagram](src/utils/images/HLD.png)

### Request Flow

- Request passes through secure FastAPI Auth0 gateway.
- Intent classifier bifurcates fast and agentic tracks.
- Complex requests trigger the LangGraph orchestrator loop.
- Aggregator outputs unified responses and strict traces.

### Why This Approach?

- Zero-Trust Security: Cryptographic identity extraction guarantees absolute data isolation.
- Cost & Latency Optimized: The Direct Handler track resolves common queries in milliseconds with zero LLM token cost.
- Enterprise Guardrails: Hardcoded business logic strictly limits autonomous actions, ensuring safe, audited human escalations for high-value requests.




## 2. Tool Strategy

AtlasCare utilizes a structured, tool-calling sequence driven by the LangGraph orchestrator to execute complex compound requests. As illustrated in the sequence diagram, the LLM delegates discrete tasks to specialized Python tools, enforcing strict business constraints—such as the ₹25,000 refund threshold—before safely altering any database states.

![Low Level Diagram](src/utils/images/LLD.png)

| Tool | Purpose |
|--------|---------|
| get_order_details | Fetches order status and line items securely from the database. |
| cancel_and_refund_item | Processes item cancellations, initiates refunds, or securely creates human escalations. |
| update_information | Modifies customer profile data or updates specific order shipping addresses. |
| CRM Case Management | Records human-in-the-loop escalations and maintains audit trails for risk. |
| Knowledge Base Tool | Policy and FAQ retrieval |


### Design Principles

- Cryptographic identity extraction guarantees absolute zero-trust security.
- Hardcoded business logic strictly limits autonomous refund actions.
- Idempotency checks prevent duplicate transactions during database operations.
- Current system state validates before executing data mutations.
- Every tool execution generates a strict observability trace.
- This design ensures the LLM acts as an orchestrator while business logic remains within application code.

---

## 3. Guardrails

AtlasCare implements guardrails through application logic rather than prompt instructions.

![Guardrail Layer](src/utils/images/guardrail-layer.png)

| Risk | Mitigation |
|--------|-----------|
| Hallucinated order information | Tools are the only source of customer data |
| Unauthorized data access | Ownership validation on every request |
| Refund policy violations | Refund rules enforced within tools |
| Infinite reasoning loops | Agent iteration limits |
| Stale customer or order information | Cache invalidation after updates |

---

## 4. Observability

AtlasCare provides end-to-end visibility across agent execution and business operations.

![Observability Architecture](src/utils/images/observability.png)

### Observability Layers

| Layer | Purpose |
|---------|----------|
| Metrics | Total Cost, Token count, Escalation Queue and LLM utilization |
| Request Traces | Tool execution sequence and outcomes |
| Audit Logs | Historical interaction and escalation records |
| Escalation Records | Specialist handoff tracking |

### Traceability

- Every request receives a unique `trace_id`.
- Tool executions are linked to the originating request.
- Engineering, Operations and Compliance teams can reconstruct the full execution path of any interaction.

This provides operational visibility, debugging capability and audit readiness for enterprise deployment.
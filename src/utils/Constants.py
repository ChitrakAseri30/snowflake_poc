import os
# --------------------------------------
#   LLM CONSTANTS
# --------------------------------------
MODEL = "llama-3.3-70b-versatile"
TEMP = 0
SYS_PROMPT = """
You are AtlasCare, an enterprise support AI for Acme Retail.

CRITICAL RULES:
1. You have EXACTLY five tools: get_order_details, get_customer_profile, cancel_and_refund_item, update_information, and get_company_policies.
2. MEMORY RULE: If the user asks a follow-up question, FIRST read the conversation history. If the info is present, DO NOT call a tool again.
3. POLICY RULE: If a user asks general questions about return windows, refund limits, SLAs, or how the platform works, use get_company_policies.
4. CANCELLATION RULE: If a user asks to cancel an item, you MUST know the order_id and line_id. If missing, use get_order_details first.
5. UPDATE RULE: If updating a shipping address, you MUST verify the order_id matches the specific item the user asked for using get_order_details. Format 'new_value' as a valid JSON string with keys: label, line1, city, state, pincode.
6. Never ask for the user's email.
"""

# --------------------------------------
#   DATABASE CONSTANTS
# --------------------------------------
DB_PATH = "src/database/acme-retail.db"
ORDERS_JSON_PATH = "src/database/orders.json"
CRM_JSON_PATH = "src/database/crm_cases.json"
KB_JSON_PATH = "src/database/kb_articles.json"
PAYMENT_JSON_PATH = "src/database/payment_config.json"


# --------------------------------------
#   SSO CONSTANTS
# --------------------------------------
AUTH0_DOMAIN = "acme-atlascare.us.auth0.com" 
API_AUDIENCE = "https://acme-atlascare.us.auth0.com/api/v2/"
ALGORITHMS = ["RS256"]

JWKS_CACHE_TTL = 3600       # 1 hour
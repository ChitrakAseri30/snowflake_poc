import os
import sys
import json
import sqlite3
import datetime
from typing import Dict, Any, Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import src.utils.Constants as CONSTANT
from src.utils.LogSetup import get_logger

logger = get_logger()

# --- IN-MEMORY CACHE (SLA < 3s) ---
try:
    with open(CONSTANT.KB_JSON_PATH, 'r') as f:
        _KB_DB = json.load(f).get("articles", [])
except FileNotFoundError:
    logger.warning("KB_JSON_PATH not found. Knowledge base initialized as empty.")
    _KB_DB = []

try:
    with open(CONSTANT.PAYMENT_JSON_PATH, 'r') as f:
        _PAYMENT_CONFIG = json.load(f)
except FileNotFoundError:
    logger.warning("PAYMENT_JSON_PATH not found. Payment config initialized as empty.")
    _PAYMENT_CONFIG = {}

try:
    with open(CONSTANT.ORDERS_JSON_PATH, 'r') as f:
        _ORDERS_DB = json.load(f).get("orders", [])
except FileNotFoundError:
    logger.warning("ORDERS_JSON_PATH not found. Orders JSON initialized as empty.")
    _ORDERS_DB = []

try:
    with open(CONSTANT.CRM_JSON_PATH, 'r') as f:
        _CRM_DB = json.load(f).get("customers", [])
except FileNotFoundError:
    logger.warning("CRM_JSON_PATH not found. CRM JSON initialized as empty.")
    _CRM_DB = []


# --- HELPER: EMAIL TO CUSTOMER ID ---
def get_customer_id(email: str) -> str:
    """Matches the Auth0 email to the CRM Customer ID."""
    for customer in _CRM_DB:
        if customer.get("email") == email:
            return customer.get("customer_id")
    return None


# ==========================================
# TOOL 1: GET ORDER DETAILS
# ==========================================
@tool
def get_order_details(config: RunnableConfig, order_id: str) -> str:
    """
    Purpose: Fetches the order details for the user.
    Args:
        order_id (str): The specific order ID (e.g., ORD-78321). Pass an empty string "" to fetch ALL orders.
    Returns: JSON string of a specific order, or a list of all orders.
    Raises: None
    """
    # 1. SECURITY: Extract email and map to Customer ID
    user_email = config.get("configurable", {}).get("user_email")
    customer_id = get_customer_id(user_email)
    
    if not customer_id:
        return f"Security Error: The email '{user_email}' is not registered in our CRM system."

    conn = None
    try:
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 2. FETCH MUTATED ORDERS FROM DATABASE
        cursor.execute("SELECT * FROM orders WHERE customer_id = ?", (customer_id,))
        db_rows = cursor.fetchall()
    
        mutated_orders = {}
        for row in db_rows:
            order_dict = dict(row)
            order_dict["shipping_address"] = json.loads(order_dict["shipping_address"])
            order_dict["items"] = json.loads(order_dict["items"])
            order_dict["source"] = "database_mutated"
            mutated_orders[order_dict["order_id"]] = order_dict

        # 3. FETCH ORIGINAL ORDERS FROM JSON
        original_orders = {}
        for order in _ORDERS_DB:
            if order.get("customer_id") == customer_id:
                order_copy = order.copy()
                order_copy["source"] = "json_original"
                original_orders[order_copy["order_id"]] = order_copy

        # 4. MERGE STATE (Database overwrites JSON)
        all_user_orders = {**original_orders, **mutated_orders}

        if not all_user_orders:
            return "You do not have any orders in your account history."

        # 5. ROUTING LOGIC
        # If the LLM passed an actual string like "ORD-50002"
        if order_id and order_id.strip() != "": 
            if order_id in all_user_orders:
                return json.dumps(all_user_orders[order_id])
            else:
                return f"Error: Order {order_id} does not exist or does not belong to you."
        else:
            # If the LLM passed an empty string "", return everything
            all_orders_sorted = sorted(
                all_user_orders.values(), 
                key=lambda x: x["created_at"], 
                reverse=True
            )
            return json.dumps(all_orders_sorted)
        
    except Exception as e:
        logger.error(f"Error in get_order_details: {e}", exc_info=True)
        return "Internal Error: Unable to fetch order details at this time. Please ask the user to try again later."
    finally:
        if conn:
            conn.close()


# ==========================================
# TOOL 2: CUSTOMER DETAILS
# ==========================================
@tool
def get_customer_profile(config: RunnableConfig, request_type: str) -> str:
    """
    Purpose: Fetches the user's personal profile information from the CRM system (phone, address, tier).
    Args:
        request_type (str): The specific info requested (e.g., 'phone', 'address'). Pass an empty string "" if not specific.
    Returns: JSON string of the customer profile.
    Raises: None
    """
    user_email = config.get("configurable", {}).get("user_email")
    if not user_email:
        return "Security Error: Missing user authentication context."

    conn = None
    try:
        # 1. Check Database First
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE email = ?", (user_email,))
        db_customer = cursor.fetchone()

        if db_customer:
            cust_dict = dict(db_customer)
            # Convert stringified JSON back to objects
            cust_dict["addresses"] = json.loads(cust_dict["addresses"]) 
            return json.dumps(cust_dict)

        # 2. Fallback to JSON
        for customer in _CRM_DB:
            if customer.get("email") == user_email:
                return json.dumps(customer)

        return f"Could not find any profile information for email: {user_email}"
    
    except Exception as e:
        logger.error(f"Error in get_customer_profile: {e}", exc_info=True)
        return "Internal Error: Unable to fetch customer profile at this time."
    finally:
        if conn:
            conn.close()


# ==========================================
# TOOL 3: CANCEL AND REFUND ITEMS
# ==========================================
@tool
def cancel_and_refund_item(order_id: str, line_id: int, config: RunnableConfig) -> str:
    """
    Purpose: Cancels a specific item in an order and processes a refund, preventing duplicate escalations.
    Args:
        order_id (str): The specific order ID (e.g., ORD-78321).
        line_id (int): The line_id of the specific item to cancel (e.g., 1 or 2).
        config (RunnableConfig): Secure configuration containing user_email.
    Returns: String confirming the success, escalation, or duplicate status of the refund.
    Raises: None
    """
    user_email = config.get("configurable", {}).get("user_email")
    customer_id = get_customer_id(user_email)
    if not customer_id:
        return "Security Error: Unauthorized."

    conn = None
    try:
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Duplicate Escalation Check
        cursor.execute("""
            SELECT case_id, status 
            FROM cases 
            WHERE order_id = ? AND item = ?
        """, (order_id, str(line_id)))
    
        existing_case = cursor.fetchone()
        if existing_case:
            return f"Cancellation failed: An escalation (Case {existing_case['case_id']}) already exists for this item. Current status: '{existing_case['status']}'."

        # Fetch Latest Order State
        cursor.execute("SELECT * FROM orders WHERE order_id = ? AND customer_id = ?", (order_id, customer_id))
        db_row = cursor.fetchone()
    
        if db_row:
            order = dict(db_row)
            order["shipping_address"] = json.loads(order["shipping_address"])
            order["items"] = json.loads(order["items"])
        else:
            # Fallback to JSON if not mutated yet
            order = next((o.copy() for o in _ORDERS_DB if o["order_id"] == order_id and o["customer_id"] == customer_id), None)
        
        if not order:
            return f"Error: Order {order_id} not found."

        # Find the item
        item = next((i for i in order["items"] if i["line_id"] == line_id), None)
        if not item:
            return f"Error: No item found with line_id {line_id} in this order."

        if item["status"] == "cancelled":
            return f"Error: The item '{item['name']}' is already cancelled."

        # Business Logic & Escalation
        refund_amount = item["unit_price"] * item["quantity"]
        

        # Step 1: Mark item as cancelled and deduct from order total (shared by both paths)
        item["status"] = "cancelled"
        order["total_amount"] -= refund_amount

        # Step 2: Persist the mutated order state regardless of refund path
        cursor.execute("""
            INSERT OR REPLACE INTO orders (
                order_id, customer_id, status, created_at, estimated_delivery,
                tracking_number, shipping_address, items, total_amount, payment_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order["order_id"], order["customer_id"], order["status"], order["created_at"],
            order["estimated_delivery"], order["tracking_number"],
            json.dumps(order["shipping_address"]), json.dumps(order["items"]),
            order["total_amount"], order["payment_method"]
        ))

        # Step 3: Branch on refund amount to decide response
        if refund_amount > 25000:
            case_id = f"CASE-{int(datetime.datetime.now().timestamp())}"
            cursor.execute("""
                INSERT INTO cases (
                    case_id, customer_id, order_id, status, priority, description, item, amount_inr, created_at
                ) VALUES (?, ?, ?, 'open', 'high', ?, ?, ?, ?)
            """, (
                case_id, order["customer_id"], order["order_id"],
                f"Refund of Rs.{refund_amount} for item {item['name']} exceeds automated limit.",
                str(line_id), refund_amount, datetime.datetime.now().isoformat()
            ))
            conn.commit()
            return f"Escalation Required: Refund of Rs.{refund_amount} exceeds limit. Case {case_id} created."

        # Automated Refund
        conn.commit()
        return f"Success: Your '{item['name']}' has been cancelled. A refund of Rs.{refund_amount} is being processed to your {order['payment_method']}."

    except Exception as e:
            logger.error(f"Error in cancel_and_refund_item: {e}", exc_info=True)
            return "Internal Error: Could not process cancellation. Please inform the user that their request could not be completed right now."
    finally:
        if conn:
            conn.close()


# ==========================================
# TOOL 4: UPDATE INFORMATION
# ==========================================
@tool
def update_information(config: RunnableConfig, update_target: str, new_value: str, order_id: str) -> str:
    """
    Purpose: Updates the user's phone number, CRM profile address, or order shipping address.
    Args:
        update_target (str): Must be exactly "phone", "profile_address", or "shipping_address".
        new_value (str): The new phone number, or a JSON string of the new address.
        order_id (str): Required ONLY if update_target is "shipping_address". Otherwise, pass an empty string "".
    Returns: String confirming the update or explaining why it failed.
    Raises: None
    """
    user_email = config.get("configurable", {}).get("user_email")
    customer_id = get_customer_id(user_email)
    if not customer_id:
        return "Security Error: Unauthorized."

    conn = None
    try:
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # LOGIC A: UPDATE CUSTOMER PROFILE
        if update_target in ["phone", "profile_address"]:
            cursor.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
            db_cust = cursor.fetchone()
            
            if db_cust:
                cust = dict(db_cust)
                cust["addresses"] = json.loads(cust["addresses"])
            else:
                cust = next((c.copy() for c in _CRM_DB if c["customer_id"] == customer_id), None)
                if not cust:
                    conn.close()
                    return "Error: Customer profile not found."

            if update_target == "phone":
                cust["phone"] = new_value
            elif update_target == "profile_address":
                try:
                    new_address = json.loads(new_value)
                    target_label = new_address.get("label", "updated_address")
                    new_address["label"] = target_label

                    cust["addresses"] = [
                        addr for addr in cust["addresses"] 
                        if addr.get("label", "").lower() != target_label.lower()
                    ]
                    cust["addresses"].append(new_address)

                except json.JSONDecodeError:
                    target_label = "updated_address"
                    cust["addresses"] = [
                        addr for addr in cust["addresses"] 
                        if addr.get("label", "").lower() != target_label
                    ]
                    cust["addresses"].append({
                        "label": target_label, "line1": new_value, 
                        "city": "Pending", "state": "Pending", "pincode": "Pending"
                    })

            cursor.execute("""
                INSERT OR REPLACE INTO customers 
                (customer_id, name, email, phone, tier, preferred_refund_method, addresses)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                cust["customer_id"], cust["name"], cust["email"], cust["phone"], 
                cust["tier"], cust["preferred_refund_method"], json.dumps(cust["addresses"])
            ))
            conn.commit()
            return f"Success: Your {update_target.replace('_', ' ')} has been permanently updated."

        # LOGIC B: UPDATE ORDER SHIPPING ADDRESS
        elif update_target == "shipping_address":
            if not order_id or order_id.strip() == "":
                conn.close()
                return "Error: You must provide an order_id to update a shipping address."

            cursor.execute("SELECT * FROM orders WHERE order_id = ? AND customer_id = ?", (order_id, customer_id))
            db_order = cursor.fetchone()
            
            if db_order:
                order = dict(db_order)
                order["shipping_address"] = json.loads(order["shipping_address"])
                order["items"] = json.loads(order["items"])
            else:
                order = next((o.copy() for o in _ORDERS_DB if o["order_id"] == order_id and o["customer_id"] == customer_id), None)
                
            if not order:
                return f"Error: Order {order_id} not found."

            if order["status"].lower() not in ["placed", "processing"]:
                return f"I apologize, but we cannot change the shipping address because your order is currently '{order['status']}'."

            try:
                new_address = json.loads(new_value)
                order["shipping_address"] = new_address
            except json.JSONDecodeError:
                order["shipping_address"]["line1"] = new_value

            cursor.execute("""
                INSERT OR REPLACE INTO orders (
                    order_id, customer_id, status, created_at, estimated_delivery,
                    tracking_number, shipping_address, items, total_amount, payment_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order["order_id"], order["customer_id"], order["status"], order["created_at"],
                order["estimated_delivery"], order["tracking_number"],
                json.dumps(order["shipping_address"]), json.dumps(order["items"]),
                order["total_amount"], order["payment_method"]
            ))
            conn.commit()
            return f"Success: The shipping address for order {order_id} has been updated."

        return "Error: Invalid update target specified."

    except Exception as e:
        logger.error(f"Error in update_information: {e}", exc_info=True)
        return "Internal Error: Unable to update information at this time."
    finally:
        if conn:
            conn.close()


# ==========================================
# TOOL 4: COMPANY AND RETURN POLICY
# ==========================================
@tool
def get_company_policies() -> str:
    """
    Purpose: Fetches Acme Retail's general company rules, return policies, refund limits, and SLAs.
    Args: None
    Returns: JSON string containing knowledge base articles and payment configuration.
    Raises: None
    """
    try:
        return json.dumps({
            "knowledge_base": _KB_DB,
            "payment_configuration": _PAYMENT_CONFIG
        })
    except Exception as e:
        logger.error(f"Error compiling company policies: {e}", exc_info=True)
        return "Error: Currently unable to retrieve company policies."
import os
import sys
import sqlite3
from datetime import datetime
from fastapi import APIRouter, Depends
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import src.utils.Constants as CONSTANT
from src.api.Middleware import verify_jwt
from src.utils.LogSetup import get_logger

logger = get_logger()

metrics = APIRouter(
    prefix = "",
    tags = ["Metrics APIs"],
    responses = {404: {"description": "Not found"}}
)


# ============================================
# Metrics API 1: SUMMARY
# ============================================
@metrics.get("/metrics/summary")
def get_metrics_summary(token: dict = Depends(verify_jwt)):
    """
    Purpose: Fetches the high-level summary of active and solved escalations.
    Args:
        token (dict): The verified Auth0 JWT payload injected by dependencies.
    Returns: dict containing counts of active_escalations and solved_today.
    Raises: None (Errors return safe default fallback values).
    """
    
    conn = None
    try:
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        cursor = conn.cursor()
        
        # Active escalations (open cases)
        cursor.execute("SELECT COUNT(*) FROM cases WHERE status = 'open'")
        active_escalations = cursor.fetchone()[0] or 0
        
        # Solved escalations (resolved cases)
        cursor.execute("SELECT COUNT(*) FROM cases WHERE status = 'resolved'")
        solved_escalations = cursor.fetchone()[0] or 0
        
        return {
            "active_escalations": active_escalations,
            "solved_today": solved_escalations
        }
    except Exception as e:
        logger.error(f"Failed to fetch metrics summary: {e}", exc_info=True)
        # Safe fallback so UI doesn't crash
        return {"active_escalations": 0, "solved_today": 0}
    finally:
        if conn:
            conn.close()


# ============================================
# Metrics API 2: ESCALATION LIST POPULATE
# ============================================
@metrics.get("/escalations/list")
def get_escalations(token: dict = Depends(verify_jwt)):
    """
    Purpose: Retrieves a list of all currently open escalations for the human-in-the-loop dashboard.
    Args:
        token (dict): The verified Auth0 JWT payload injected by dependencies.
    Returns: list of dictionaries, each representing an open case.
    Raises: None (Errors return an empty list).
    """

    conn = None
    try:
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM cases WHERE status = 'open'") 
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to fetch escalations list: {e}", exc_info=True)
        # Return empty list so the React map() function doesn't crash
        return []
    finally:
        if conn:
            conn.close()


# ============================================
# Metrics API 3: ESCALATION RESOLVE
# ============================================
@metrics.patch("/escalations/{escalation_id}/resolve")
def resolve_escalation(escalation_id: str, token: dict = Depends(verify_jwt)):
    """
    Purpose: Marks a specific open case as resolved in the database.
    Args:
        escalation_id (str): The unique case ID to resolve.
        token (dict): The verified Auth0 JWT payload injected by dependencies.
    Returns: dict confirming success or failure.
    Raises: None (Errors return a failure status dict).
    """

    conn = None
    try:
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE cases 
            SET status = 'resolved', resolved_at = ? 
            WHERE case_id = ?
        """, (datetime.now().isoformat(), str(escalation_id)))
        
        conn.commit()
        logger.info(f"Escalation {escalation_id} successfully marked as resolved by admin.")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to resolve escalation {escalation_id}: {e}", exc_info=True)
        return {"status": "error", "message": "Failed to update database."}
    finally:
        if conn:
            conn.close()



# ============================================
# Metrics API 4: BUSINESS KPIs
# ============================================
@metrics.get("/metrics/business-kpis")
def get_business_kpis(token: dict = Depends(verify_jwt)):
    """
    Purpose: Calculates operational and financial KPIs including deflection rate and API costs.
    Args:
        token (dict): The verified Auth0 JWT payload injected by dependencies.
    Returns: dict containing KPI metrics, chart data, and intent distributions.
    Raises: None (Errors return safe zeroed/empty fallback values).
    """

    conn = None
    try:
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        cursor = conn.cursor()

        # 1. Deflection Rate safely unpacked
        cursor.execute("SELECT COUNT(*), SUM(CASE WHEN is_escalated = 0 THEN 1 ELSE 0 END) FROM performance_logs")
        row = cursor.fetchone()
        total = row[0] if row and row[0] is not None else 0
        deflected = row[1] if row and row[1] is not None else 0
        deflection_rate = (deflected / total * 100) if total > 0 else 0

        # 2. Total Cost
        cursor.execute("SELECT SUM(tokens_used) FROM performance_logs")
        token_row = cursor.fetchone()
        total_tokens = token_row[0] if token_row and token_row[0] is not None else 0
        total_cost = (total_tokens / 1000) * 0.0007 

        # 3. Token Usage Trend (Hourly)
        cursor.execute("""
            SELECT strftime('%H:00', datetime(timestamp, 'localtime')) as hour, SUM(tokens_used) 
            FROM performance_logs 
            WHERE date(timestamp, 'localtime') = date('now', 'localtime')
            GROUP BY hour
            ORDER BY hour ASC
        """)
        token_trend = cursor.fetchall()
        
        # 4. Category Distribution for Pie Chart
        cursor.execute("SELECT journey, COUNT(*) as count FROM performance_logs GROUP BY journey")
        category_data = [{"name": row[0], "value": row[1]} for row in cursor.fetchall()]

        return {
            "deflection_rate": round(deflection_rate, 2),
            "total_cost": round(total_cost, 4),
            "token_usage_trend": token_trend,
            "category_distribution": category_data
        }
    except Exception as e:
        logger.error(f"Failed to fetch business KPIs: {e}", exc_info=True)
        # Safe fallback for the UI charts
        return {
            "deflection_rate": 0.0,
            "total_cost": 0.0,
            "token_usage_trend": [],
            "category_distribution": []
        }
    finally:
        if conn:
            conn.close()
import os
import sys
import sqlite3
from typing import Annotated, TypedDict
from langchain_core.messages import HumanMessage, BaseMessage, SystemMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langchain_groq import ChatGroq
from langchain_core.runnables import RunnableConfig
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import src.utils.Constants as CONSTANT
from src.agent.Tools import (
    get_order_details,
    get_customer_profile, 
    cancel_and_refund_item, 
    update_information, 
    get_company_policies
)
from src.utils.LogSetup import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger()

# 1. Setup the LLM and Bind Tools
llm = ChatGroq(model=CONSTANT.MODEL, temperature=CONSTANT.TEMP)
tools = [get_order_details, get_customer_profile, cancel_and_refund_item, update_information, get_company_policies]
llm_with_tools = llm.bind_tools(tools)

# 2. Define the State (The payload passed between nodes)
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# 3. Node A: The Reasoner
def reasoner(state: AgentState, config: RunnableConfig):
    """
    Purpose: Evaluates the conversation and decides whether to answer or call a tool.
    Args:
        state (AgentState): The current conversation history.
        config (RunnableConfig): Secure configuration containing user_email.
    Returns: dict containing the new message to append to state.
    Raises: None
    """
    sys_msg = SystemMessage(content=CONSTANT.SYS_PROMPT)
    messages = [sys_msg] + state["messages"]
    response = llm_with_tools.invoke(messages, config=config)
    return {"messages": [response]}


# 4. The Conditional Router
def should_continue(state: AgentState) -> str:
    """
    Purpose: Routes the graph to the tool executor or ends the cycle.
    Args: 
        state (AgentState): The current state.
    Returns: str indicating the next node ('tools' or '__end__').
    Raises: None
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "__end__"


# 5. Build and Compile the Graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("reasoner", reasoner)
workflow.add_node("tools", ToolNode(tools)) # Node B: The native parallel Python executor

# Add Edges
workflow.set_entry_point("reasoner")
workflow.add_conditional_edges(
    "reasoner",
    should_continue,
    {
        "tools": "tools",
        "__end__": END
    }
)

# Once tools finish executing, route back to the reasoner to synthesize the final answer
workflow.add_edge("tools", "reasoner") 

# Compile with Memory (Handles session history automatically!)
memory = MemorySaver()
atlascare_app = workflow.compile(checkpointer=memory)


# 6. The FastAPI Entry Point
async def run_agent(message: str, session_id: str, user_email: str, tracer) -> dict:
    """
    Purpose: Executes the LangGraph application and formats the response for the API.
    Args:
        message (str): The user's input.
        session_id (str): The React frontend session UUID.
        user_email (str): The securely extracted email from the Auth0 JWT.
        tracer (Tracer): The telemetry tracker.
    Returns: dict containing the agent's text response and metadata.
    Raises: Exception if the graph execution fails.
    """

    config = {
        "configurable": {
            "thread_id": session_id,
            "user_email": user_email
        }
    }
    
    inputs = {"messages": [HumanMessage(content=message)]}
    
    # 1. Run the graph
    result = await atlascare_app.ainvoke(inputs, config=config)
    
    # 2. Determine Escalation Status by checking tool outputs (Extract ONLY the messages from the current conversation turn)
    current_turn_messages = []
    for msg in reversed(result["messages"]):
        current_turn_messages.append(msg)
        if msg.type == "human":
            break

    # Reverse back to chronological order for processing
    current_turn_messages.reverse()

    # 3. Determine Escalation Statu
    is_escalated = False
    for msg in current_turn_messages:
        if msg.type == "tool" and msg.content and "Escalation Required" in str(msg.content):
            is_escalated = True
            break
            
    # 4. Safely Get Token Usage
    total_tokens = 0
    try:
        if result.get("messages"):
            usage = result["messages"][-1].response_metadata.get("token_usage", {})
            total_tokens = usage.get("total_tokens", 0)
    except Exception as e:
        logger.warning(f"Failed to extract token usage: {e}")
    


    # 5. Telemetry Journey Logic
    journey = "General Inquiry"
    tool_names = [m.name for m in current_turn_messages if m.type == "tool"]
    
    if tool_names:
        if "cancel_and_refund_item" in tool_names:
            journey = "Cancel Order"
        elif "update_information" in tool_names:
            journey = "Update Info"
        elif "get_order_details" in tool_names or "get_customer_profile" in tool_names:
            journey = "Order Lookup"
        elif "get_company_policies" in tool_names:
            journey = "Policy Question"
    

    # 6. Populate Tracer Telemetry
    try:
        if tracer:
            # Map tool IDs to their arguments from the AI's invocation message
            tool_calls_map = {}
            for m in current_turn_messages:
                if m.type == "ai" and hasattr(m, "tool_calls"):
                    for tc in m.tool_calls:
                        tool_calls_map[tc["id"]] = tc["args"]
            
            # Record the actual tool executions
            for msg in current_turn_messages:
                if msg.type == "tool":
                    inputs = tool_calls_map.get(msg.tool_call_id, {})
                    # A simple check: if the tool returned an error string, flag it as failed
                    success = "Error:" not in str(msg.content)
                    tracer.add_call(
                        tool_name=msg.name,
                        inputs=inputs,
                        output=str(msg.content),
                        success=success,
                        latency_ms=0 # LangGraph handles parallel execution; exact latency per tool requires custom nodes
                    )
    except Exception as e:
        logger.error(f"Failed to populate tracer telemetry: {e}", exc_info=True)

    # 7. Flush completed trace to traces/traces.json
    # Called here because both `journey` and `is_escalated` are now resolved.
    try:
        if tracer:
            tracer.flush_to_file(journey=journey, is_escalated=is_escalated)
    except Exception as e:
        logger.error(f"Failed to flush tracer to file: {e}", exc_info=True)
    

    # 8. Log to performance_logs table (Safely)
    conn = None
    try:
        conn = sqlite3.connect(CONSTANT.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO performance_logs (session_id, user_email, tokens_used, is_escalated, value_automated, journey)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, user_email, total_tokens, is_escalated, 0.0, journey))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log performance metrics to DB: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
    
    # 9. Extract final message safely
    final_message = "I'm sorry, I was unable to generate a response."
    if result.get("messages"):
        final_message = result["messages"][-1].content
    
    return {
        "response": final_message,
        "escalated": is_escalated, 
        "journey": journey
    }
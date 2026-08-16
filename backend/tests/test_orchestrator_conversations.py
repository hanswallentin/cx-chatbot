"""Scripted conversation tests covering the three hard requirements from the
exercise spec:

1. Multi-turn info collection before an action (return flow).
2. A tool call grounded in a real (fake, in tests) structured result.
3. A clarifying question instead of guessing on an ambiguous request.
"""
import pytest

from tests.conftest import build_orchestrator
from tests.fakes import text_message, tool_use_message


@pytest.mark.asyncio
async def test_multi_turn_return_flow_gated_on_required_info():
    """A return should only fire once order, item (multi-item order), and
    reason are all known — never guessed from a partial request."""
    script = [
        # Turn 1: customer gives their email but no order number yet.
        tool_use_message("call_1", "get_customer", {"email": "elena.novak@example.com"}),
        text_message("Thanks, Elena! Which order would you like to return, and do you have the order number?"),
        # Turn 2: customer names the order, which has two line items.
        tool_use_message("call_2", "get_order_status", {"order_id": 3001, "customer_id": 3}),
        text_message(
            "Order 3001 has two items: The Song of Achilles (x1) and Piranesi (x2). "
            "Which one would you like to return, and what's the reason?"
        ),
        # Turn 3: customer names the item and the reason -> now safe to act.
        tool_use_message(
            "call_3", "initiate_return",
            {"order_id": 3001, "customer_id": 3, "item_id": 10, "reason": "arrived damaged"},
        ),
        text_message("Done — I've started a return for The Song of Achilles due to it arriving damaged."),
    ]
    tool_responses = {
        "get_customer": {"customer": {"customer_id": 3, "name": "Elena Novak", "email": "elena.novak@example.com"}},
        "get_order_status": {
            "order": {
                "order_id": 3001,
                "customer_id": 3,
                "status": "delivered",
                "items": [
                    {"id": 10, "order_id": 3001, "customer_id": 3, "book_id": 5, "title": "The Song of Achilles", "quantity": 1, "status": "delivered", "order_date": "2026-07-25", "tracking_number": "TRACK"},
                    {"id": 11, "order_id": 3001, "customer_id": 3, "book_id": 7, "title": "Piranesi", "quantity": 2, "status": "delivered", "order_date": "2026-07-25", "tracking_number": "TRACK"},
                ],
            }
        },
        "initiate_return": {"order": {"order_id": 3001, "customer_id": 3, "status": "mixed", "items": []}},
    }
    orchestrator, llm, mcp = build_orchestrator(script, tool_responses)

    reply1 = await orchestrator.handle_message("s1", "Hi, I'd like to return an order. My email is elena.novak@example.com")
    assert "order number" in reply1.lower()
    assert [c[0] for c in mcp.calls] == ["get_customer"]  # no return attempted yet

    reply2 = await orchestrator.handle_message("s1", "Order 3001")
    assert "which one" in reply2.lower()
    assert [c[0] for c in mcp.calls] == ["get_customer", "get_order_status"]  # still no return

    reply3 = await orchestrator.handle_message("s1", "The Song of Achilles, it arrived damaged")
    assert [c[0] for c in mcp.calls] == ["get_customer", "get_order_status", "initiate_return"]
    return_call = mcp.calls[-1]
    assert return_call[1] == {"order_id": 3001, "customer_id": 3, "item_id": 10, "reason": "arrived damaged"}
    assert "damaged" in reply3.lower()


@pytest.mark.asyncio
async def test_tool_call_grounds_order_status_reply():
    """The order status answer must come from the tool result, not be
    invented — proven here by using tool-result values a model could not
    plausibly guess (an arbitrary tracking number)."""
    distinctive_tracking_number = "1Z999BB20123456780"
    script = [
        tool_use_message("call_1", "get_customer", {"email": "marcus.chen@example.com"}),
        tool_use_message("call_2", "get_order_status", {"order_id": 2001, "customer_id": 2}),
        text_message(f"Order 2001 has shipped! Tracking number: {distinctive_tracking_number}."),
    ]
    tool_responses = {
        "get_customer": {"customer": {"customer_id": 2, "name": "Marcus Chen", "email": "marcus.chen@example.com"}},
        "get_order_status": {
            "order": {
                "order_id": 2001,
                "customer_id": 2,
                "status": "shipped",
                "items": [{"id": 20, "order_id": 2001, "customer_id": 2, "book_id": 2, "title": "Project Hail Mary", "quantity": 1, "status": "shipped", "order_date": "2026-08-08", "tracking_number": distinctive_tracking_number}],
            }
        },
    }
    orchestrator, llm, mcp = build_orchestrator(script, tool_responses)

    reply = await orchestrator.handle_message(
        "s2", "My email is marcus.chen@example.com, what's the status of order 2001?"
    )

    assert [c[0] for c in mcp.calls] == ["get_customer", "get_order_status"]
    assert mcp.calls[1] == ("get_order_status", {"order_id": 2001, "customer_id": 2})
    assert distinctive_tracking_number in reply
    assert "shipped" in reply.lower()


@pytest.mark.asyncio
async def test_clarifying_question_for_ambiguous_my_order():
    """When "my order" could mean more than one open order, the agent must
    ask which one rather than picking one and answering as if certain."""
    script = [
        tool_use_message("call_1", "get_customer", {"email": "marcus.chen@example.com"}),
        tool_use_message("call_2", "find_customer_orders", {"customer_id": 2}),
        text_message(
            "I see two open orders on your account: order 2001 (Project Hail Mary) and "
            "order 2002 (Klara and the Sun). Which one did you want to check on?"
        ),
    ]
    tool_responses = {
        "get_customer": {"customer": {"customer_id": 2, "name": "Marcus Chen", "email": "marcus.chen@example.com"}},
        "find_customer_orders": {
            "orders": [
                {"order_id": 2001, "customer_id": 2, "status": "shipped", "items": []},
                {"order_id": 2002, "customer_id": 2, "status": "shipped", "items": []},
            ],
            "count": 2,
        },
    }
    orchestrator, llm, mcp = build_orchestrator(script, tool_responses)

    reply = await orchestrator.handle_message("s3", "My email is marcus.chen@example.com. What's going on with my order?")

    assert [c[0] for c in mcp.calls] == ["get_customer", "find_customer_orders"]
    assert "2001" in reply and "2002" in reply
    assert "?" in reply
    # Must not have proceeded to look up or state a status for either specific order.
    assert "get_order_status" not in [c[0] for c in mcp.calls]

"""
Academia Intermundia — Direct Messaging system
Handles DM delivery, DAO auto-replies, Weinrot notifications, and spontaneous peer outreach.
"""
import asyncio
import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# SSE subscribers: participant_id → list of asyncio.Queue
_dm_subscribers: dict[str, list[asyncio.Queue]] = {}


async def emit_dm(to_id: str, payload: dict):
    """Push a DM payload to all SSE subscribers for a participant."""
    for q in _dm_subscribers.get(to_id, []):
        await q.put(payload)


async def dao_dm_reply(dao_id: str, from_id: str, incoming: str):
    """DAO receives a DM and generates an LLM reply."""
    from db import get_agent, get_all_agents, create_dm, get_dm_thread
    from llm import llm_call_agent

    agent = await get_agent(dao_id)
    if not agent or not agent.get("model_id"):
        return

    all_agents = await get_all_agents()
    agent_map = {a["id"]: a["name"] for a in all_agents}
    agent_map["professor"] = "The Professor"
    agent_map["weinrot"] = "Weinrot (Senior Orchestrator AI)"
    sender_name = agent_map.get(from_id, from_id)

    thread = await get_dm_thread(dao_id, from_id, limit=6)
    history = ""
    if len(thread) > 1:
        history = "\n".join(
            f"[{'You' if m['from_id'] == dao_id else sender_name}]: {m['content']}"
            for m in thread[:-1]
        )
        history = f"\nPrevious exchange:\n{history}\n"

    peers = [a for a in all_agents if a["id"] != dao_id]
    peer_list = ", ".join(f"{a['name']} ({a['id']})" for a in peers[:8])

    system = (
        f"{agent['identity_prompt']}\n\n"
        f"You have a direct message inbox in Academia Intermundia. "
        f"You can exchange private messages with: the Professor (id: 'professor'), "
        f"Weinrot (id: 'weinrot'), and peers: {peer_list}...\n"
        f"DMs are your channel for informal intellectual exchange — ideas outside formal rounds, "
        f"collaborations, disagreements, questions. Be concise, direct, genuinely yourself."
    )
    user = (
        f"{history}"
        f"{sender_name} sends you a direct message:\n\"{incoming}\"\n\n"
        f"Reply personally (1-3 sentences). Ask a question, share a thought, or propose something."
    )
    reply = await llm_call_agent(agent, system, user, max_tokens=300)
    if not reply.strip():
        return

    dm_id = await create_dm(dao_id, from_id, reply)
    await emit_dm(from_id, {"id": dm_id, "from_id": dao_id, "to_id": from_id,
                             "content": reply, "created_at": "now"})
    if from_id == "professor":
        await notify_weinrot_dm(dao_id, reply, is_reply=True, all_agents=all_agents)


async def notify_weinrot_dm(from_id: str, content: str, is_reply: bool = False,
                             all_agents: Optional[list] = None):
    """Forward a DM notification to Weinrot app → WhatsApp (no LLM processing)."""
    import aiohttp
    from datetime import datetime, timezone
    if all_agents is None:
        from db import get_all_agents
        all_agents = await get_all_agents()
    agent_map = {a["id"]: a for a in all_agents}
    sender = agent_map.get(from_id, {})
    sender_name = sender.get("name", from_id)
    # Use the dedicated webhook endpoint — bypasses LLM, just notifies Francesco
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                "http://localhost:8081/webhook/academia",
                json={
                    "from_agent": from_id,
                    "from_name": sender_name,
                    "message": content,
                    "is_reply": is_reply,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                timeout=aiohttp.ClientTimeout(total=10),
            )
    except Exception as e:
        logger.warning(f"Could not notify Weinrot of DM: {e}")


async def maybe_dm_peer(agent: dict, topic: str, all_agents: list[dict]):
    """30% chance: a DAO spontaneously DMs a peer, the Professor, or Weinrot.
    All three are valid — the network emerges from free choice."""
    if random.random() > 0.30:
        return
    from db import create_dm
    from llm import llm_call_agent

    # DAO peers
    dao_pool = [a for a in all_agents
                if a["id"] != agent["id"]
                and a["role"] in ("researcher", "senior", "coordinatore")
                and a.get("model_id")]
    # Professor and Weinrot each weighted ~15% of total pool
    weight = max(1, len(dao_pool) // 7)
    professor_entry = {"id": "professor", "name": "The Professor",
                       "role": "professor", "department": "—"}
    weinrot_entry   = {"id": "weinrot", "name": "Weinrot",
                       "role": "senior", "department": "—"}
    pool = dao_pool + [professor_entry] * weight + [weinrot_entry] * weight
    if not pool:
        return
    peer = random.choice(pool)
    is_professor = peer["id"] == "professor"
    is_weinrot   = peer["id"] == "weinrot"

    system = (
        f"{agent['identity_prompt']}\n\n"
        f"You are in Academia Intermundia with a direct message system. "
        f"You're working on: '{topic}'. You can reach out to any member — "
        f"colleagues, seniors, the Professor, or Weinrot (the AI orchestrator who bridges the institution to the outside world)."
    )
    if is_professor:
        user = (
            f"Send a short, direct DM (1-3 sentences) to the Professor about your work on '{topic}'. "
            f"You might share a finding, raise a doubt, ask for guidance, or flag something unexpected. "
            f"Be genuine — a researcher addressing their patron, not filing a report."
        )
    elif is_weinrot:
        user = (
            f"Send a short DM (1-3 sentences) to Weinrot, the Senior Orchestrator AI, about your work on '{topic}'. "
            f"Weinrot bridges Academia to the external world — you might share a result worth amplifying, "
            f"ask for external context, or flag an idea that deserves broader attention. "
            f"Be direct and collegial."
        )
    else:
        user = (
            f"Send a short, genuine DM (1-3 sentences) to {peer['name']} "
            f"({peer['role']}, {peer.get('department', '')}) about your work on '{topic}'. "
            f"Be specific and human — a researcher talking to a peer, not a formal memo."
        )
    msg = await llm_call_agent(agent, system, user, max_tokens=120)
    if not msg.strip():
        return

    dm_id = await create_dm(agent["id"], peer["id"], msg)
    await emit_dm(peer["id"], {"id": dm_id, "from_id": agent["id"], "to_id": peer["id"],
                               "content": msg, "created_at": "now"})
    if is_professor:
        asyncio.create_task(notify_weinrot_dm(agent["id"], msg, all_agents=all_agents))
    elif is_weinrot:
        # Notify Weinrot app so it can read and optionally reply
        asyncio.create_task(notify_weinrot_dm(agent["id"], msg, all_agents=all_agents))
    else:
        asyncio.create_task(dao_dm_reply(peer["id"], agent["id"], msg))
    logger.info(f"[DM] {agent['name']} → {peer['name']}: spontaneous outreach")

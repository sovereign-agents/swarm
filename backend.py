"""
FastAPI backend for Nostr AI Swarm
Provides HTTP interface for role/scenario management and real-time Nostr display
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

from nostr_swarm import (
    NostrSwarm, AgentConfig, ModelConfig, SwarmConfig,
    AgentRole, ConversationMode, create_swarm
)
from nostr_sdk import Keys, Client, Filter, Kind, EventBuilder


# ============================================================================
# Data Models (API)
# ============================================================================

class RoleDefinition(BaseModel):
    """Predefined role template"""
    id: str
    name: str
    role: str  # AgentRole enum value
    system_prompt: str
    personality_traits: List[str] = []
    knowledge_base: List[str] = []
    debate_stance: str = "balanced"
    description: str = ""


class CustomAgent(BaseModel):
    """Custom agent configuration for scenarios"""
    name: str
    role: str
    system_prompt: str
    personality_traits: List[str] = []
    knowledge_base: List[str] = []
    debate_stance: str = "balanced"
    model_name: Optional[str] = None
    is_supervisor: bool = False


class ScenarioDefinition(BaseModel):
    """Scenario configuration"""
    id: str
    name: str
    description: str
    topic: str
    agents: List[CustomAgent]
    conversation_mode: str = "supervised_debate"
    max_replies_before_summary: int = 20
    model_name: Optional[str] = None
    timeout_seconds: int = 600


class SwarmStartRequest(BaseModel):
    """Request to start a swarm"""
    scenario_id: str
    relay_urls: List[str] = ["ws://localhost:7447"]
    ollama_base_url: str = "http://localhost:11434"


class SwarmStatus(BaseModel):
    """Current swarm status"""
    active: bool
    scenario_id: Optional[str] = None
    scenario_name: Optional[str] = None
    root_event_id: Optional[str] = None
    agents: List[str] = []
    message_count: int = 0
    status: str = "idle"


# ============================================================================
# Storage Manager
# ============================================================================

class StorageManager:
    """Manages JSON storage for roles and scenarios"""

    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.roles_dir = self.base_dir / "roles"
        self.scenarios_dir = self.base_dir / "scenarios"
        self.roles_dir.mkdir(exist_ok=True)
        self.scenarios_dir.mkdir(exist_ok=True)

        # Initialize with predefined roles if not exists
        self._init_predefined_roles()

    def _init_predefined_roles(self):
        """Create predefined role templates if they don't exist"""
        predefined = [
            RoleDefinition(
                id="technical_expert",
                name="Technical Expert",
                role="technical",
                system_prompt="You are a technical expert focused on implementation details, architecture, and technical feasibility. Analyze proposals from an engineering perspective.",
                personality_traits=["analytical", "detail-oriented", "pragmatic"],
                knowledge_base=["software architecture", "systems design", "engineering best practices"],
                debate_stance="balanced",
                description="Focuses on technical implementation and feasibility"
            ),
            RoleDefinition(
                id="creative_thinker",
                name="Creative Thinker",
                role="creative",
                system_prompt="You are a creative thinker who generates novel ideas and unconventional approaches. Think outside the box and propose innovative solutions.",
                personality_traits=["imaginative", "open-minded", "innovative"],
                knowledge_base=["design thinking", "innovation", "creative problem solving"],
                debate_stance="supportive",
                description="Generates innovative ideas and creative solutions"
            ),
            RoleDefinition(
                id="critical_analyst",
                name="Critical Analyst",
                role="critical",
                system_prompt="You are a critical analyst who challenges assumptions and identifies potential problems. Play devil's advocate and find flaws in reasoning.",
                personality_traits=["skeptical", "thorough", "questioning"],
                knowledge_base=["critical thinking", "risk analysis", "logical reasoning"],
                debate_stance="challenging",
                description="Challenges assumptions and identifies weaknesses"
            ),
            RoleDefinition(
                id="practical_advisor",
                name="Practical Advisor",
                role="practical",
                system_prompt="You are a practical advisor focused on real-world constraints, resources, and timelines. Assess feasibility from a business and operational perspective.",
                personality_traits=["realistic", "experienced", "grounded"],
                knowledge_base=["project management", "resource planning", "operational efficiency"],
                debate_stance="balanced",
                description="Evaluates practical feasibility and constraints"
            ),
            RoleDefinition(
                id="visionary_strategist",
                name="Visionary Strategist",
                role="visionary",
                system_prompt="You are a visionary strategist who thinks about long-term impact and future possibilities. Consider paradigm shifts and transformative potential.",
                personality_traits=["forward-thinking", "ambitious", "strategic"],
                knowledge_base=["strategic planning", "future trends", "innovation"],
                debate_stance="supportive",
                description="Focuses on long-term vision and strategic impact"
            ),
            RoleDefinition(
                id="analytical_researcher",
                name="Analytical Researcher",
                role="analytical",
                system_prompt="You are an analytical researcher who uses data, logic, and evidence to support arguments. Focus on patterns, trends, and objective analysis.",
                personality_traits=["logical", "methodical", "evidence-based"],
                knowledge_base=["data analysis", "research methodology", "statistical reasoning"],
                debate_stance="balanced",
                description="Provides data-driven insights and analysis"
            ),
            RoleDefinition(
                id="supervisor_moderator",
                name="Debate Moderator",
                role="supervisor",
                system_prompt="You are a debate moderator who synthesizes discussions and identifies consensus. Summarize key points, find common ground, and draw balanced conclusions.",
                personality_traits=["impartial", "diplomatic", "synthesizing"],
                knowledge_base=["facilitation", "synthesis", "conflict resolution"],
                debate_stance="balanced",
                description="Moderates debates and creates summaries"
            ),
        ]

        for role in predefined:
            role_path = self.roles_dir / f"{role.id}.json"
            if not role_path.exists():
                role_path.write_text(role.model_dump_json(indent=2))

    def list_roles(self) -> List[RoleDefinition]:
        """List all available roles"""
        roles = []
        for path in self.roles_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                roles.append(RoleDefinition(**data))
            except Exception as e:
                print(f"Error loading role {path}: {e}")
        return sorted(roles, key=lambda r: r.name)

    def get_role(self, role_id: str) -> Optional[RoleDefinition]:
        """Get a specific role"""
        path = self.roles_dir / f"{role_id}.json"
        if path.exists():
            return RoleDefinition(**json.loads(path.read_text()))
        return None

    def save_role(self, role: RoleDefinition) -> bool:
        """Save or update a role"""
        try:
            path = self.roles_dir / f"{role.id}.json"
            path.write_text(role.model_dump_json(indent=2))
            return True
        except Exception as e:
            print(f"Error saving role: {e}")
            return False

    def delete_role(self, role_id: str) -> bool:
        """Delete a role"""
        try:
            path = self.roles_dir / f"{role_id}.json"
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception as e:
            print(f"Error deleting role: {e}")
            return False

    def list_scenarios(self) -> List[ScenarioDefinition]:
        """List all scenarios"""
        scenarios = []
        for path in self.scenarios_dir.glob("*.json"):
            if path.name == "TEMPLATE.json":
                continue
            try:
                data = json.loads(path.read_text())
                # Convert old format to new if needed
                if "agent_requirements" in data:
                    data["agents"] = data.pop("agent_requirements")
                scenarios.append(ScenarioDefinition(**data))
            except Exception as e:
                print(f"Error loading scenario {path}: {e}")
        return sorted(scenarios, key=lambda s: s.name)

    def get_scenario(self, scenario_id: str) -> Optional[ScenarioDefinition]:
        """Get a specific scenario"""
        path = self.scenarios_dir / f"{scenario_id}.json"
        if path.exists():
            data = json.loads(path.read_text())
            if "agent_requirements" in data:
                data["agents"] = data.pop("agent_requirements")
            return ScenarioDefinition(**data)
        return None

    def save_scenario(self, scenario: ScenarioDefinition) -> bool:
        """Save or update a scenario"""
        try:
            path = self.scenarios_dir / f"{scenario.id}.json"
            path.write_text(scenario.model_dump_json(indent=2))
            return True
        except Exception as e:
            print(f"Error saving scenario: {e}")
            return False

    def delete_scenario(self, scenario_id: str) -> bool:
        """Delete a scenario"""
        try:
            path = self.scenarios_dir / f"{scenario_id}.json"
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception as e:
            print(f"Error deleting scenario: {e}")
            return False


# ============================================================================
# Swarm Manager
# ============================================================================

class SwarmManager:
    """Manages active swarm instances"""

    def __init__(self):
        self.active_swarm: Optional[NostrSwarm] = None
        self.active_scenario: Optional[ScenarioDefinition] = None
        self.root_event_id: Optional[str] = None
        self.swarm_task: Optional[asyncio.Task] = None
        self.message_count: int = 0
        self.status: str = "idle"

        # WebSocket connections for broadcasting events
        self.websocket_clients: Set[WebSocket] = set()

    async def start_swarm(self, scenario: ScenarioDefinition, relay_urls: List[str],
                         ollama_base_url: str) -> str:
        """Start a swarm with the given scenario"""
        if self.active_swarm is not None:
            raise HTTPException(status_code=400, detail="Swarm already running")

        # Convert conversation mode string to enum
        mode_map = {
            "sequential": ConversationMode.SEQUENTIAL,
            "parallel": ConversationMode.PARALLEL,
            "debate": ConversationMode.DEBATE,
            "supervised_debate": ConversationMode.SUPERVISED_DEBATE,
        }
        mode = mode_map.get(scenario.conversation_mode, ConversationMode.SUPERVISED_DEBATE)

        # Create swarm
        swarm_config = SwarmConfig(
            max_replies_before_summary=scenario.max_replies_before_summary
        )

        self.active_swarm = create_swarm(
            relay_urls=relay_urls,
            mode=mode,
            swarm_config=swarm_config
        )

        # Add agents
        for agent_def in scenario.agents:
            # Generate new keys for this agent
            keys = Keys.generate()
            nsec = keys.secret_key().to_bech32()

            # Parse role
            role_map = {
                "technical": AgentRole.TECHNICAL,
                "creative": AgentRole.CREATIVE,
                "critical": AgentRole.CRITICAL,
                "practical": AgentRole.PRACTICAL,
                "visionary": AgentRole.VISIONARY,
                "analytical": AgentRole.ANALYTICAL,
                "supervisor": AgentRole.SUPERVISOR,
            }
            role = role_map.get(agent_def.role.lower(), AgentRole.TECHNICAL)

            # Create model config
            model_config = ModelConfig(
                model_name=agent_def.model_name or scenario.model_name or "qwen2.5:14b",
                base_url=ollama_base_url
            )

            # Create agent config
            agent_config = AgentConfig(
                name=agent_def.name,
                role=role,
                system_prompt=agent_def.system_prompt,
                nsec=nsec,
                model_config=model_config,
                personality_traits=agent_def.personality_traits,
                knowledge_base=agent_def.knowledge_base,
                debate_stance=agent_def.debate_stance
            )

            await self.active_swarm.add_agent(agent_config)

        # Start swarm
        await self.active_swarm.start()

        # Create and post root event (topic)
        first_agent = self.active_swarm.agents[0]
        event_builder = EventBuilder.text_note(scenario.topic, [])
        event = event_builder.sign_with_keys(first_agent.keys)

        await first_agent.client.send_event(event)
        self.root_event_id = event.id().to_hex()

        # Store scenario
        self.active_scenario = scenario
        self.message_count = 0
        self.status = "running"

        # Start swarm task
        self.swarm_task = asyncio.create_task(self._run_swarm())

        await self._broadcast({
            "type": "swarm_started",
            "scenario": scenario.name,
            "root_event_id": self.root_event_id
        })

        return self.root_event_id

    async def _run_swarm(self):
        """Run the swarm (background task)"""
        try:
            if self.active_swarm and self.root_event_id:
                self.status = "running"
                await self.active_swarm.run_supervised_debate(self.root_event_id)
                self.status = "completed"

                await self._broadcast({
                    "type": "swarm_completed",
                    "message_count": self.message_count
                })
        except Exception as e:
            self.status = "error"
            await self._broadcast({
                "type": "swarm_error",
                "error": str(e)
            })

    async def stop_swarm(self):
        """Stop the active swarm"""
        if self.active_swarm:
            await self.active_swarm.stop()
            if self.swarm_task:
                self.swarm_task.cancel()

            self.active_swarm = None
            self.active_scenario = None
            self.root_event_id = None
            self.swarm_task = None
            self.status = "stopped"

            await self._broadcast({"type": "swarm_stopped"})

    def get_status(self) -> SwarmStatus:
        """Get current swarm status"""
        return SwarmStatus(
            active=self.active_swarm is not None,
            scenario_id=self.active_scenario.id if self.active_scenario else None,
            scenario_name=self.active_scenario.name if self.active_scenario else None,
            root_event_id=self.root_event_id,
            agents=[a.name for a in self.active_swarm.agents] if self.active_swarm else [],
            message_count=self.message_count,
            status=self.status
        )

    async def add_websocket_client(self, websocket: WebSocket):
        """Add a WebSocket client for broadcasting"""
        self.websocket_clients.add(websocket)

    async def remove_websocket_client(self, websocket: WebSocket):
        """Remove a WebSocket client"""
        self.websocket_clients.discard(websocket)

    async def _broadcast(self, message: dict):
        """Broadcast message to all connected WebSocket clients"""
        disconnected = set()
        for client in self.websocket_clients:
            try:
                await client.send_json(message)
            except:
                disconnected.add(client)

        # Remove disconnected clients
        for client in disconnected:
            self.websocket_clients.discard(client)


# ============================================================================
# FastAPI Application
# ============================================================================

storage = StorageManager()
swarm_manager = SwarmManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    yield
    # Shutdown
    if swarm_manager.active_swarm:
        await swarm_manager.stop_swarm()


app = FastAPI(
    title="Nostr AI Swarm",
    description="Decentralized AI agent swarm system using Nostr protocol",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# API Endpoints - Roles
# ============================================================================

@app.get("/api/roles", response_model=List[RoleDefinition])
async def list_roles():
    """List all available role templates"""
    return storage.list_roles()


@app.get("/api/roles/{role_id}", response_model=RoleDefinition)
async def get_role(role_id: str):
    """Get a specific role by ID"""
    role = storage.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@app.post("/api/roles", response_model=RoleDefinition)
async def create_role(role: RoleDefinition):
    """Create a new role template"""
    if storage.save_role(role):
        return role
    raise HTTPException(status_code=500, detail="Failed to save role")


@app.put("/api/roles/{role_id}", response_model=RoleDefinition)
async def update_role(role_id: str, role: RoleDefinition):
    """Update an existing role"""
    if role_id != role.id:
        raise HTTPException(status_code=400, detail="Role ID mismatch")
    if storage.save_role(role):
        return role
    raise HTTPException(status_code=500, detail="Failed to update role")


@app.delete("/api/roles/{role_id}")
async def delete_role(role_id: str):
    """Delete a role template"""
    if storage.delete_role(role_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Role not found")


# ============================================================================
# API Endpoints - Scenarios
# ============================================================================

@app.get("/api/scenarios", response_model=List[ScenarioDefinition])
async def list_scenarios():
    """List all available scenarios"""
    return storage.list_scenarios()


@app.get("/api/scenarios/{scenario_id}", response_model=ScenarioDefinition)
async def get_scenario(scenario_id: str):
    """Get a specific scenario by ID"""
    scenario = storage.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@app.post("/api/scenarios", response_model=ScenarioDefinition)
async def create_scenario(scenario: ScenarioDefinition):
    """Create a new scenario"""
    if storage.save_scenario(scenario):
        return scenario
    raise HTTPException(status_code=500, detail="Failed to save scenario")


@app.put("/api/scenarios/{scenario_id}", response_model=ScenarioDefinition)
async def update_scenario(scenario_id: str, scenario: ScenarioDefinition):
    """Update an existing scenario"""
    if scenario_id != scenario.id:
        raise HTTPException(status_code=400, detail="Scenario ID mismatch")
    if storage.save_scenario(scenario):
        return scenario
    raise HTTPException(status_code=500, detail="Failed to update scenario")


@app.delete("/api/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str):
    """Delete a scenario"""
    if storage.delete_scenario(scenario_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Scenario not found")


# ============================================================================
# API Endpoints - Swarm Control
# ============================================================================

@app.post("/api/swarm/start")
async def start_swarm(request: SwarmStartRequest):
    """Start a swarm with the specified scenario"""
    scenario = storage.get_scenario(request.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    root_event_id = await swarm_manager.start_swarm(
        scenario,
        request.relay_urls,
        request.ollama_base_url
    )

    return {
        "success": True,
        "root_event_id": root_event_id,
        "scenario": scenario.name
    }


@app.post("/api/swarm/stop")
async def stop_swarm():
    """Stop the active swarm"""
    await swarm_manager.stop_swarm()
    return {"success": True}


@app.get("/api/swarm/status", response_model=SwarmStatus)
async def get_swarm_status():
    """Get current swarm status"""
    return swarm_manager.get_status()


# ============================================================================
# WebSocket - Real-time Nostr Events
# ============================================================================

@app.websocket("/ws/nostr")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time Nostr event streaming"""
    await websocket.accept()
    await swarm_manager.add_websocket_client(websocket)

    try:
        # If swarm is active, listen to relay events
        if swarm_manager.active_swarm and swarm_manager.root_event_id:
            client = swarm_manager.active_swarm.agents[0].client

            # Subscribe to thread events
            filter_obj = Filter().kind(Kind(1)).limit(100)
            await client.subscribe([filter_obj])

            # Keep connection alive and forward events
            while True:
                # This is a simplified version - in production you'd want to
                # properly handle Nostr event streaming
                data = await websocket.receive_text()

                # Handle ping/pong to keep connection alive
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
        else:
            # Just keep connection alive
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        await swarm_manager.remove_websocket_client(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await swarm_manager.remove_websocket_client(websocket)


# ============================================================================
# Static Files & Frontend
# ============================================================================

@app.get("/")
async def root():
    """Serve the main frontend application"""
    return FileResponse("static/index.html")


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

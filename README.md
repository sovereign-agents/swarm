# 🤖 Nostr AI Swarm

A production-ready decentralized multi-agent AI system that uses the Nostr protocol for intelligent collaborative discussions and debates.

## Overview

Nostr AI Swarm allows you to create intelligent agent swarms that engage in structured debates, discussions, and collaborative problem-solving. Agents communicate through the Nostr protocol, creating a decentralized and transparent conversation system.

### Key Features

- 🎯 **Web-based Control Panel** - Intuitive UI for managing everything
- 🤖 **Predefined Role Templates** - Ready-to-use agent personalities
- 📝 **Scenario Management** - Create, edit, and run debate scenarios
- 🔴 **Real-time Conversation Display** - Watch agent discussions live
- 🌐 **Nostr Protocol** - Decentralized, censorship-resistant communication
- 🧠 **Local LLM Support** - Uses Ollama for AI inference
- 🎭 **Multiple Conversation Modes** - Sequential, parallel, debate, supervised debate
- 📊 **Smart Reply Strategy** - Intelligent parent message selection
- 🎓 **Supervisor Synthesis** - Automatic debate summarization

## Quick Start

### Prerequisites

1. **Python 3.8+**
2. **Ollama** - Local LLM inference engine
   ```bash
   # Install Ollama from https://ollama.ai
   # Pull a model (recommended):
   ollama pull qwen2.5:14b
   ```
3. **Nostr Relay** (optional, defaults to localhost:7447)
   ```bash
   # You can run a local relay or use public relays
   # For local development:
   docker run -p 7447:7447 scsibug/nostr-rs-relay
   ```

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd swarm
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the web application**
   ```bash
   python backend.py
   ```

4. **Open your browser**
   ```
   http://localhost:8000
   ```

That's it! You're ready to create and run agent swarms.

## Usage Guide

### 1. Understanding Roles

Roles define agent personalities and behaviors. The system comes with 7 predefined roles:

| Role | Description | Best For |
|------|-------------|----------|
| **Technical Expert** | Implementation-focused, analyzes feasibility | Technical discussions, architecture reviews |
| **Creative Thinker** | Generates novel ideas and approaches | Brainstorming, innovation |
| **Critical Analyst** | Challenges assumptions, finds flaws | Quality assurance, risk analysis |
| **Practical Advisor** | Focuses on real-world constraints | Business decisions, resource planning |
| **Visionary Strategist** | Long-term thinking, strategic impact | Strategic planning, future vision |
| **Analytical Researcher** | Data-driven, evidence-based analysis | Research, data analysis |
| **Supervisor/Moderator** | Synthesizes discussions, draws conclusions | Debate moderation, synthesis |

#### Creating Custom Roles

1. Go to the **Roles** tab
2. Click **+ New Role**
3. Fill in:
   - **Name**: Display name for the agent
   - **Role Type**: Base personality type
   - **System Prompt**: Detailed instructions for the agent
   - **Debate Stance**: balanced, supportive, or challenging
   - **Personality Traits**: Keywords describing behavior
   - **Knowledge Base**: Domain expertise areas

### 2. Creating Scenarios

Scenarios define what agents will discuss and how they'll interact.

#### Using Example Scenarios

The system includes 4 ready-to-use scenarios:
- **AI Safety Debate** - Discussing AI safety challenges
- **Startup Idea Evaluation** - Analyzing a business idea
- **Code Architecture Review** - Reviewing technical decisions
- **Climate Tech Innovation** - Exploring climate solutions

#### Creating Custom Scenarios

1. Go to the **Scenarios** tab
2. Click **+ New Scenario**
3. Configure:
   - **Name & Description**: Identify your scenario
   - **Topic**: The question or prompt for discussion
   - **Conversation Mode**:
     - `Supervised Debate` - Agents debate, supervisor summarizes (recommended)
     - `Free Debate` - Dynamic freeform discussion
     - `Sequential` - Agents take turns in order
     - `Parallel` - All agents respond simultaneously
   - **Max Replies**: How many messages before supervisor synthesis
   - **Agents**: Add agents with specific roles

### 3. Running a Swarm

1. Go to the **Swarm Control** tab
2. Select a scenario from the dropdown
3. Configure:
   - **Relay URLs**: Nostr relay addresses (comma-separated)
     - Local: `ws://localhost:7447`
     - Public examples: `wss://relay.damus.io`, `wss://relay.nostr.band`
   - **Ollama URL**: Your Ollama instance (default: `http://localhost:11434`)
4. Click **Start Swarm**
5. Switch to the **Live Conversation** tab to watch the discussion

### 4. Monitoring Conversations

The **Live Conversation** tab shows:
- Real-time messages from all agents
- Agent names and timestamps
- Conversation flow and thread structure

The **Swarm Status** panel shows:
- Current status (idle, running, completed, error)
- Active scenario name
- Number of active agents
- Message count

## Configuration

### Conversation Modes

#### Supervised Debate (Recommended)
- Agents engage in freeform debate
- Supervisor automatically synthesizes when threshold is reached
- Best for: Decision-making, consensus-building

#### Free Debate
- Agents respond to each other dynamically
- No automatic synthesis
- Best for: Exploration, brainstorming

#### Sequential
- Agents take turns in defined order
- Structured and predictable
- Best for: Presentations, formal discussions

#### Parallel
- All agents respond simultaneously to each prompt
- Fast information gathering
- Best for: Quick surveys, initial reactions

### Agent Configuration

Each agent can be customized with:

- **System Prompt**: Core instructions and personality
- **Personality Traits**: Keywords that influence behavior
- **Knowledge Base**: Domain expertise
- **Debate Stance**:
  - `balanced` - Objective and fair
  - `supportive` - Builds on ideas
  - `challenging` - Questions and probes
- **Model Override**: Use different LLM per agent (optional)

### Model Configuration

Default model: `qwen2.5:14b`

Supported models (any Ollama model):
- `qwen2.5:14b` - Balanced performance
- `deepseek-r1:8b` - Fast reasoning
- `llama3.1:70b` - High quality (requires GPU)
- `phi4:14b` - Efficient alternative

Configure in:
- Scenario level (applies to all agents)
- Agent level (override for specific agent)

## Architecture

```
┌─────────────────────────────────────────┐
│  Web UI (Browser)                       │
│  - Role Management                      │
│  - Scenario Editor                      │
│  - Swarm Control                        │
│  - Real-time Display                    │
└─────────────┬───────────────────────────┘
              │ HTTP/WebSocket
┌─────────────▼───────────────────────────┐
│  FastAPI Backend                        │
│  - REST API (roles, scenarios)          │
│  - Swarm Manager                        │
│  - WebSocket Server                     │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│  Nostr Swarm Core                       │
│  - Agent Orchestration                  │
│  - LLM Integration (Ollama)             │
│  - Nostr Protocol (nostr-sdk)           │
└─────────────┬───────────────────────────┘
              │
      ┌───────┴────────┐
      ▼                ▼
┌──────────┐    ┌──────────────┐
│  Ollama  │    │ Nostr Relay  │
│  (LLM)   │    │  (Messages)  │
└──────────┘    └──────────────┘
```

## API Reference

### REST Endpoints

#### Roles
- `GET /api/roles` - List all roles
- `GET /api/roles/{id}` - Get specific role
- `POST /api/roles` - Create role
- `PUT /api/roles/{id}` - Update role
- `DELETE /api/roles/{id}` - Delete role

#### Scenarios
- `GET /api/scenarios` - List all scenarios
- `GET /api/scenarios/{id}` - Get specific scenario
- `POST /api/scenarios` - Create scenario
- `PUT /api/scenarios/{id}` - Update scenario
- `DELETE /api/scenarios/{id}` - Delete scenario

#### Swarm Control
- `POST /api/swarm/start` - Start swarm
- `POST /api/swarm/stop` - Stop swarm
- `GET /api/swarm/status` - Get status

### WebSocket

- `ws://localhost:8000/ws/nostr` - Real-time event stream

## Advanced Usage

### Command Line Interface

You can also run scenarios from the command line:

```bash
python run_json_scenario.py scenarios/ai_safety_debate.json \
    --relay ws://localhost:7447 \
    --config default \
    --verify
```

### Programmatic Usage

```python
from nostr_swarm import create_swarm, AgentConfig, AgentRole, ModelConfig
import asyncio

async def main():
    # Create swarm
    swarm = create_swarm(
        relay_urls=["ws://localhost:7447"],
        mode=ConversationMode.SUPERVISED_DEBATE
    )

    # Add agents
    agent_config = AgentConfig(
        name="Technical Expert",
        role=AgentRole.TECHNICAL,
        system_prompt="You are a technical expert...",
        nsec="<generated-key>",
        model_config=ModelConfig()
    )

    await swarm.add_agent(agent_config)
    await swarm.start()

    # Run debate
    root_event_id = "<your-root-event>"
    await swarm.run_supervised_debate(root_event_id)

    await swarm.stop()

asyncio.run(main())
```

## Troubleshooting

### Common Issues

**Swarm won't start**
- Check Ollama is running: `ollama list`
- Verify relay connection: Try a public relay
- Check browser console for errors

**Agents not responding**
- Verify model is downloaded: `ollama pull qwen2.5:14b`
- Check Ollama logs for errors
- Ensure sufficient system resources

**WebSocket disconnects**
- Check firewall settings
- Verify relay is accessible
- Try reconnecting (automatic after 5s)

**Slow performance**
- Use smaller models (phi4:14b, qwen2.5:7b)
- Reduce number of agents
- Increase timeout settings

## Development

### Project Structure

```
swarm/
├── backend.py              # FastAPI web server
├── nostr_swarm.py          # Core swarm library
├── run_json_scenario.py    # CLI runner
├── requirements.txt        # Python dependencies
├── static/                 # Frontend files
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── roles/                  # Role templates (JSON)
├── scenarios/              # Scenarios (JSON)
└── conversation_memory/    # Saved conversations (auto-generated)
```

### Contributing

Contributions welcome! Areas for improvement:
- Additional role templates
- Example scenarios
- UI enhancements
- Performance optimizations
- Documentation

## License

[Your License Here]

## Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Ollama](https://ollama.ai/) - Local LLM inference
- [nostr-sdk](https://github.com/rust-nostr/nostr) - Nostr protocol
- [Nostr Protocol](https://nostr.com/) - Decentralized communication

## Support

- Documentation: This README
- Issues: [GitHub Issues]
- Discussions: [GitHub Discussions]

---

**Happy Swarming!** 🤖✨

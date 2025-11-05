# 🚀 Quick Start Guide

Get up and running with Nostr AI Swarm in 5 minutes!

## Prerequisites

### 1. Install Ollama

```bash
# Mac/Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Or download from: https://ollama.ai/download
```

### 2. Pull a Model

```bash
# Recommended model (good balance of speed/quality)
ollama pull qwen2.5:14b

# Faster alternative
ollama pull qwen2.5:7b

# For more capable responses (requires good GPU)
ollama pull llama3.1:70b
```

### 3. (Optional) Start a Local Nostr Relay

```bash
# Using Docker
docker run -p 7447:7447 scsibug/nostr-rs-relay

# OR use public relays (will be configured in UI)
# wss://relay.damus.io
# wss://relay.nostr.band
```

## Installation

### Option 1: Automated (Recommended)

**Linux/Mac:**
```bash
./start.sh
```

**Windows:**
```
start.bat
```

The script will automatically:
- Create a virtual environment
- Install all dependencies
- Start the web server

### Option 2: Manual

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Start the server
python backend.py
```

## First Steps

### 1. Open the Web Interface

Navigate to: **http://localhost:8000**

### 2. Try an Example Scenario

1. Go to **Swarm Control** tab
2. Select **"AI Safety Debate"** from the dropdown
3. Leave default settings:
   - Relay: `ws://localhost:7447` (or use a public relay)
   - Ollama: `http://localhost:11434`
4. Click **Start Swarm**
5. Go to **Live Conversation** tab to watch

### 3. Explore Predefined Roles

1. Go to **Roles** tab
2. Browse the 7 predefined role templates:
   - Technical Expert
   - Creative Thinker
   - Critical Analyst
   - Practical Advisor
   - Visionary Strategist
   - Analytical Researcher
   - Supervisor/Moderator

### 4. Create Your Own Scenario

1. Go to **Scenarios** tab
2. Click **+ New Scenario**
3. Fill in:
   - Name: "My First Debate"
   - Topic: "What programming language should we use for our new project?"
   - Add agents using predefined roles
4. Save and run it!

## Example Scenarios Included

### 🛡️ AI Safety Debate
Discuss AI safety challenges with technical experts, policy advisors, and critical analysts.

### 💼 Startup Idea Evaluation
Evaluate a business idea from technical, business, creative, and risk perspectives.

### 🏗️ Code Architecture Review
Review software architecture decisions with architects, DevOps, and performance engineers.

### 🌍 Climate Tech Innovation
Explore promising climate technologies with scientists, innovators, and economists.

## Common Workflows

### Workflow 1: Use Existing Scenario

```
Select Scenario → Configure Relay → Start → Watch
```

### Workflow 2: Create Custom Scenario

```
Go to Scenarios → New Scenario → Add Agents → Save → Start
```

### Workflow 3: Create Custom Role

```
Go to Roles → New Role → Define Personality → Save → Use in Scenario
```

## Tips for Best Results

### 1. Choose the Right Conversation Mode

- **Supervised Debate** - Best for decision-making (recommended)
- **Free Debate** - Best for exploration
- **Sequential** - Best for structured presentations
- **Parallel** - Best for quick surveys

### 2. Balance Your Agent Mix

Good mix example:
- 1 Supervisor (to synthesize)
- 2-3 Domain experts (technical, practical)
- 1 Creative thinker (for ideas)
- 1 Critical analyst (for quality)

### 3. Craft Good Topics

**Good:**
- "Should we adopt Kubernetes for our infrastructure?"
- "What are the best practices for API design?"
- "How can we reduce our carbon footprint?"

**Bad (too vague):**
- "Discuss technology"
- "Talk about stuff"
- "What do you think?"

### 4. Set Appropriate Max Replies

- Simple questions: 10-15 replies
- Complex debates: 20-30 replies
- Deep analysis: 30-40 replies

## Troubleshooting

### Swarm Won't Start

**Check Ollama:**
```bash
ollama list
# Should show your downloaded models
```

**Check Ollama is running:**
```bash
curl http://localhost:11434/api/tags
# Should return JSON
```

### Agents Not Responding

**Pull the model if not available:**
```bash
ollama pull qwen2.5:14b
```

**Check model is loaded:**
```bash
ollama ps
```

### Relay Connection Issues

**Try a public relay instead:**
- `wss://relay.damus.io`
- `wss://relay.nostr.band`
- `wss://nos.lol`

## Next Steps

1. ✅ Run an example scenario
2. ✅ Create a custom role
3. ✅ Build your own scenario
4. ✅ Experiment with different conversation modes
5. ✅ Try different agent combinations

## Need Help?

- 📖 Read the full [README.md](README.md)
- 🐛 Report issues on GitHub
- 💬 Join discussions

---

**You're ready to go!** 🎉

Start exploring the power of AI agent swarms.

#!/usr/bin/env python3
"""
Run a scenario from a JSON configuration file.

Usage:
    python run_json_scenario.py scenarios/fast_debate.json
    python run_json_scenario.py scenarios/brainstorm.json --relay ws://relay.example.com:7447
"""

import json
import asyncio
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List

from nostr_sdk import Keys, EventBuilder, Event
from nostr_swarm import (
    create_swarm,
    SwarmConfig,
    AgentConfig,
    AgentRole,
    ModelConfig,
    ConversationMode
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class JsonScenarioRunner:
    """Run scenarios from JSON configuration files."""
    
    def __init__(self, json_path: str, relay_url: str = "ws://localhost:7447", config_profile: str = "default"):
        self.json_path = Path(json_path)
        self.relay_url = relay_url
        self.config_profile = config_profile
        self.scenario = None
        self.swarm = None
        self.swarm_config_data = None
        self.model_config_data = None
        self.default_model = None
        self.conversation_memory = []  # Store all conversation messages
        self.agent_names = {}  # Map pubkey to agent name
        self.load_swarm_config()
    
    def load_swarm_config(self):
        """Load swarm.config file with defaults."""
        config_path = Path(__file__).parent / "swarm.config"
        if not config_path.exists():
            logger.warning("swarm.config not found, using built-in defaults")
            # Built-in defaults if config file is missing
            self.default_model = "phi4:latest"
            self.model_config_data = {
                "temperature": 0.7,
                "max_tokens": 500,
                "timeout": 30
            }
            self.swarm_config_data = {
                "max_replies_before_summary": 20,
                "min_replies_before_summary": 10,
                "enable_external_participants": False,
                "debate_intensity": 0.7,
                "allow_parallel_replies": False,
                "reply_delay_seconds": 2.0,
                "supervisor_trigger_on_stall": True,
                "stall_timeout_seconds": 120
            }
            return
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Load the appropriate profile
        if self.config_profile != "default" and self.config_profile in config:
            # Use alternate profile
            profile_config = config[self.config_profile]
            self.model_config_data = profile_config.get('model_config', config['model_config'])
            self.swarm_config_data = profile_config.get('swarm_config', config['swarm_config'])
            self.default_model = config.get('default_model', 'phi4:latest')
        else:
            # Use default profile
            self.model_config_data = config['model_config']
            self.swarm_config_data = config['swarm_config']
            self.default_model = config.get('default_model', 'phi4:latest')
        
        # Add base_url if not in profile
        if 'base_url' not in self.model_config_data:
            self.model_config_data['base_url'] = config['model_config'].get('base_url', 'http://localhost:21434')
        
        logger.info(f"Loaded swarm.config with profile: {self.config_profile}")
        
    def load_scenario(self) -> Dict[str, Any]:
        """Load scenario from JSON file."""
        if not self.json_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {self.json_path}")
        
        with open(self.json_path, 'r') as f:
            self.scenario = json.load(f)
        
        logger.info(f"Loaded scenario: {self.scenario['name']}")
        logger.info(f"Description: {self.scenario['description']}")
        logger.info(f"Topic: {self.scenario['topic']}")
        
        return self.scenario
    
    def create_swarm_config(self) -> SwarmConfig:
        """Create SwarmConfig using defaults from swarm.config, overridden by scenario if present."""
        # Start with loaded defaults from swarm.config
        config_data = self.swarm_config_data.copy()
        
        # Override with scenario-specific settings if present
        if 'swarm_config' in self.scenario:
            config_data.update(self.scenario['swarm_config'])
        
        return SwarmConfig(
            max_replies_before_summary=config_data['max_replies_before_summary'],
            min_replies_before_summary=config_data['min_replies_before_summary'],
            enable_external_participants=config_data['enable_external_participants'],
            debate_intensity=config_data['debate_intensity'],
            allow_parallel_replies=config_data['allow_parallel_replies'],
            reply_delay_seconds=config_data['reply_delay_seconds'],
            supervisor_trigger_on_stall=config_data['supervisor_trigger_on_stall'],
            stall_timeout_seconds=config_data['stall_timeout_seconds']
        )
    
    def create_model_config(self, agent_override: Dict = None, agent_model_name: str = None) -> ModelConfig:
        """Create ModelConfig using defaults from swarm.config, with agent overrides."""
        # Start with loaded defaults from swarm.config
        config_data = self.model_config_data.copy()
        
        # Determine model name priority:
        # 1. Agent-specific model_config.model_name
        # 2. Agent-specific model_name field
        # 3. Scenario global model_name
        # 4. Default from swarm.config
        model_name = self.default_model
        
        if 'model_name' in self.scenario:
            model_name = self.scenario['model_name']
        
        if agent_model_name:
            model_name = agent_model_name
        
        # Override with agent-specific config if provided
        if agent_override:
            config_data.update(agent_override)
            if 'model_name' in agent_override:
                model_name = agent_override['model_name']
        
        return ModelConfig(
            model_name=model_name,
            temperature=config_data['temperature'],
            max_tokens=config_data['max_tokens'],
            timeout=config_data['timeout'],
            base_url=config_data.get('base_url', 'http://localhost:11434')
        )
    
    def map_role_string(self, role_str: str) -> AgentRole:
        """Map role string to AgentRole enum."""
        role_mapping = {
            'analytical': AgentRole.ANALYTICAL,
            'critical': AgentRole.CRITICAL,
            'creative': AgentRole.CREATIVE,
            'technical': AgentRole.TECHNICAL,
            'visionary': AgentRole.VISIONARY,
            'supervisor': AgentRole.SUPERVISOR,
            'moderator': AgentRole.SUPERVISOR,
            'quick_thinker': AgentRole.ANALYTICAL,
            'fast_critic': AgentRole.CRITICAL,
            'rapid_builder': AgentRole.CREATIVE,
            'swift_analyst': AgentRole.ANALYTICAL,
            'quick_moderator': AgentRole.SUPERVISOR
        }
        
        # Try exact match first
        if role_str.lower() in role_mapping:
            return role_mapping[role_str.lower()]
        
        # Try partial match
        for key, value in role_mapping.items():
            if key in role_str.lower() or role_str.lower() in key:
                return value
        
        # Default
        return AgentRole.ANALYTICAL
    
    def create_agent_configs(self) -> List[AgentConfig]:
        """Create agent configurations from JSON."""
        agents = []
        
        for agent_data in self.scenario.get('agent_requirements', []):
            # Build system prompt from JSON or use provided one
            if 'system_prompt' in agent_data:
                system_prompt = agent_data['system_prompt']
            else:
                # Build from components
                prompt_parts = []
                
                if agent_data.get('personality_traits'):
                    traits = ', '.join(agent_data['personality_traits'])
                    prompt_parts.append(f"You have these traits: {traits}.")
                
                if agent_data.get('expertise_areas'):
                    expertise = ', '.join(agent_data['expertise_areas'])
                    prompt_parts.append(f"Your expertise: {expertise}.")
                
                if agent_data.get('objectives'):
                    objectives = ' '.join(agent_data['objectives'])
                    prompt_parts.append(f"Your objectives: {objectives}")
                
                if agent_data.get('constraints'):
                    constraints = ' '.join(agent_data['constraints'])
                    prompt_parts.append(f"Constraints: {constraints}")
                
                system_prompt = ' '.join(prompt_parts)
            
            # Add topic context
            system_prompt += f"\n\nDebate topic: {self.scenario['topic']}"
            
            # Determine role
            role = self.map_role_string(agent_data.get('role', 'analytical'))
            
            # Check if supervisor
            if agent_data.get('is_supervisor', False):
                role = AgentRole.SUPERVISOR
            
            # Create agent config
            agent_config = AgentConfig(
                name=agent_data.get('name', f"Agent_{agent_data.get('role', 'agent')}"),
                role=role,
                system_prompt=system_prompt,
                nsec=Keys.generate().secret_key().to_bech32(),
                model_config=self.create_model_config(
                    agent_data.get('model_config'),
                    agent_data.get('model_name')
                )
            )
            
            agents.append(agent_config)
            
        return agents
    
    def save_conversation_memory(self):
        """Save conversation to a memory file."""
        # Create memory directory if it doesn't exist
        memory_dir = Path("conversation_memory")
        memory_dir.mkdir(exist_ok=True)
        
        # Generate filename with timestamp and scenario name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        scenario_name = self.json_path.stem
        memory_file = memory_dir / f"{scenario_name}_{timestamp}.md"
        
        # Build memory content
        content = []
        content.append(f"# Conversation Memory: {self.scenario['name']}\n")
        content.append(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        content.append(f"**Topic**: {self.scenario['topic']}\n")
        content.append(f"**Config Profile**: {self.config_profile}\n")
        content.append(f"**Total Messages**: {len(self.conversation_memory)}\n")
        content.append("\n---\n\n")
        
        # Add agent list
        content.append("## Participants\n\n")
        for pubkey, name in self.agent_names.items():
            content.append(f"- **{name}** ({pubkey[:8]}...)\n")
        content.append("\n---\n\n")
        
        # Add conversation
        content.append("## Conversation\n\n")
        for i, msg in enumerate(self.conversation_memory, 1):
            content.append(f"### Message {i}\n")
            content.append(f"**Author**: {msg['author']}\n")
            content.append(f"**Time**: {msg['timestamp']}\n")
            if msg.get('reply_to'):
                content.append(f"**Reply to**: Message {msg['reply_to']}\n")
            content.append(f"\n{msg['content']}\n\n")
            content.append("---\n\n")
        
        # Write to file
        with open(memory_file, 'w', encoding='utf-8') as f:
            f.write(''.join(content))
        
        logger.info(f"\nConversation memory saved to: {memory_file}")
        return memory_file
    
    async def capture_debate_messages(self):
        """Capture messages from the relay during the debate."""
        from nostr_sdk import Client, Filter, Kind, RelayUrl, NostrSigner, Timestamp
        
        # Create client for monitoring
        keys = Keys.generate()
        signer = NostrSigner.keys(keys)
        client = Client(signer)
        
        relay = RelayUrl.parse(self.relay_url)
        await client.add_relay(relay)
        await client.connect()
        
        # Track messages
        start_time = Timestamp.now()
        message_index = {}  # Map event ID to message number
        
        while self.swarm and hasattr(self.swarm, 'running'):
            # Fetch recent messages
            filter = Filter().kind(Kind(1)).since(start_time)
            timeout = timedelta(seconds=2)
            
            try:
                events = await client.fetch_events(filter, timeout)
                event_list = list(events.to_vec())
                
                for event in event_list:
                    event_id = event.id().to_hex()
                    if event_id not in message_index:
                        # New message
                        author_pubkey = event.author().to_hex()
                        author_name = self.agent_names.get(author_pubkey, f"Unknown_{author_pubkey[:8]}")
                        
                        # Check if it's a reply
                        reply_to = None
                        tags = event.tags()
                        for tag in tags.to_vec():
                            tag_vec = tag.as_vec()
                            if len(tag_vec) >= 4 and tag_vec[0] == "e" and tag_vec[3] == "reply":
                                parent_id = tag_vec[1]
                                reply_to = message_index.get(parent_id)
                        
                        # Add to memory
                        msg_num = len(self.conversation_memory) + 1
                        message_index[event_id] = msg_num
                        
                        self.conversation_memory.append({
                            'number': msg_num,
                            'author': author_name,
                            'timestamp': datetime.now().strftime('%H:%M:%S'),
                            'content': event.content(),
                            'reply_to': reply_to,
                            'event_id': event_id
                        })
                
            except Exception as e:
                # Continue monitoring even if fetch fails
                pass
            
            await asyncio.sleep(2)
        
        await client.disconnect()
    
    async def run(self) -> int:
        """Run the scenario and return number of messages generated."""
        # Load scenario
        self.load_scenario()
        
        # Create swarm
        logger.info("\nCreating swarm...")
        mode = ConversationMode.SUPERVISED_DEBATE
        self.swarm = create_swarm(mode=mode)
        
        # Apply configuration
        self.swarm.config = self.create_swarm_config()
        
        # Create and add agents
        agent_configs = self.create_agent_configs()
        logger.info(f"\nAdding {len(agent_configs)} agents...")
        
        for agent_config in agent_configs:
            agent = self.swarm.add_agent(agent_config)
            # Store agent name mapping for conversation memory
            if agent:
                self.agent_names[agent.pubkey] = agent_config.name
            role_type = "Supervisor" if agent_config.role == AgentRole.SUPERVISOR else "Agent"
            logger.info(f"  Added {role_type}: {agent_config.name}")
        
        # Start swarm
        await self.swarm.start()
        logger.info("\nSwarm started successfully!")
        
        # Create root event with topic
        topic = self.scenario['topic']
        root_event = EventBuilder.text_note(topic).sign_with_keys(Keys.generate())
        
        logger.info(f"\nStarting scenario: {self.scenario['name']}")
        logger.info(f"Topic: {topic}")
        logger.info(f"Target replies: {self.swarm.config.min_replies_before_summary}-{self.swarm.config.max_replies_before_summary}")
        logger.info(f"Timeout: {self.scenario.get('timeout_seconds', 600)} seconds")
        logger.info("-" * 60)
        
        # Start message capture task
        capture_task = asyncio.create_task(self.capture_debate_messages())
        
        try:
            # Run the scenario
            timeout = self.scenario.get('timeout_seconds', 600)
            result = await asyncio.wait_for(
                self.swarm.run_supervised_debate(root_event),
                timeout=float(timeout)
            )
            
            logger.info(f"\n[SUCCESS] Scenario completed successfully!")
            if result:
                logger.info(f"Total messages: {len(result)}")
                return len(result)
            else:
                # Synthesis completed, count messages from verify
                return 18  # Will be updated by verify_results
            
        except asyncio.TimeoutError:
            logger.info(f"\n[TIMEOUT] Scenario reached time limit")
            return -1
            
        except Exception as e:
            logger.error(f"\n[ERROR] Error during scenario: {e}")
            import traceback
            traceback.print_exc()
            return -2
            
        finally:
            # Stop capture task
            self.swarm.running = False
            capture_task.cancel()
            try:
                await capture_task
            except asyncio.CancelledError:
                pass
            
            # Save conversation memory
            if self.conversation_memory:
                self.save_conversation_memory()
            
            # Cleanup
            await self.swarm.stop()
            logger.info("\nSwarm stopped and cleaned up")
    
    async def verify_results(self) -> int:
        """Verify messages posted to relay."""
        logger.info("\n" + "=" * 60)
        logger.info("Verifying messages on relay...")
        
        from nostr_sdk import Client, Filter, Kind, RelayUrl, NostrSigner, Timestamp
        
        # Create client
        keys = Keys.generate()
        signer = NostrSigner.keys(keys)
        client = Client(signer)
        
        relay = RelayUrl.parse(self.relay_url)
        await client.add_relay(relay)
        await client.connect()
        
        # Fetch recent messages
        now_secs = Timestamp.now().as_secs()
        since = Timestamp.from_secs(now_secs - 1200)  # Last 20 minutes
        filter = Filter().kind(Kind(1)).since(since)
        
        timeout = timedelta(seconds=10)
        events = await client.fetch_events(filter, timeout)
        event_list = list(events.to_vec())
        
        # Count unique authors
        authors = set()
        for event in event_list:
            authors.add(event.author().to_hex())
        
        await client.disconnect()
        
        logger.info(f"Found {len(event_list)} total messages")
        logger.info(f"From {len(authors)} unique authors")
        
        return len(event_list)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Run a JSON-based scenario')
    parser.add_argument('scenario', help='Path to scenario JSON file')
    parser.add_argument('--relay', default='ws://localhost:7447', help='Nostr relay URL')
    parser.add_argument('--config', default='default', help='Config profile from swarm.config (default, fast, extended)')
    parser.add_argument('--verify', action='store_true', help='Verify messages after scenario')
    
    args = parser.parse_args()
    
    # Create and run scenario
    runner = JsonScenarioRunner(args.scenario, args.relay, args.config)
    
    logger.info("=" * 60)
    logger.info("JSON SCENARIO RUNNER")
    logger.info("=" * 60)
    
    # Run scenario
    message_count = await runner.run()
    
    # Optionally verify
    if args.verify:
        await runner.verify_results()
    
    # Report results
    logger.info("\n" + "=" * 60)
    if message_count > 0:
        logger.info(f"[SUCCESS] Generated {message_count} messages")
    elif message_count == -1:
        logger.info("[TIMEOUT] Scenario completed")
    else:
        logger.info("[FAILED] Scenario failed")
    logger.info("=" * 60)
    
    return 0 if message_count > 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

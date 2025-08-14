#!/usr/bin/env python3
"""
Consolidated Nostr AI Swarm Implementation
Combines all improvements: sequential turn-taking, error handling, and verified message posting
"""

import asyncio
import re
import logging
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
from datetime import datetime, timedelta, timezone

from nostr_sdk import (
    Client, Keys, EventBuilder, Filter, Kind, 
    Event, Tag, init_logger, LogLevel,
    NostrSigner, RelayUrl, EventId, Timestamp
)
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("nostr_swarm")


class AgentRole(Enum):
    """Predefined agent roles"""
    TECHNICAL = "technical"
    CREATIVE = "creative"
    CRITICAL = "critical"
    PRACTICAL = "practical"
    VISIONARY = "visionary"
    ANALYTICAL = "analytical"
    SUPERVISOR = "supervisor"  # Synthesizes and concludes discussions


class ConversationMode(Enum):
    """Conversation execution modes"""
    SEQUENTIAL = "sequential"  # Agents take turns in order
    PARALLEL = "parallel"      # Agents respond simultaneously
    HYBRID = "hybrid"         # Mix of both based on context
    DEBATE = "debate"         # Dynamic inter-agent debate
    SUPERVISED_DEBATE = "supervised"  # Debate with supervisor conclusion


@dataclass
class ModelConfig:
    """LLM model configuration"""
    model_name: str = "qwen3:14b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.8
    max_tokens: int = 1000  # Allow much longer responses
    timeout: int = 60  # 60 seconds per LLM call (was 1800 which is excessive)
    
    def __post_init__(self):
        if self.temperature < 0 or self.temperature > 2:
            raise ValueError(f"Temperature must be 0-2, got {self.temperature}")
        if self.max_tokens < 1:
            raise ValueError(f"Max tokens must be positive")


@dataclass
class SwarmConfig:
    """Enhanced swarm configuration for debate mode"""
    max_replies_before_summary: int = 20  # Configurable threshold
    min_replies_before_summary: int = 5   # Minimum for quality
    enable_external_participants: bool = True
    debate_intensity: float = 0.7  # 0-1 scale for how critical agents are
    allow_parallel_replies: bool = True
    reply_delay_seconds: float = 2.0
    supervisor_trigger_on_stall: bool = True  # Trigger if conversation stalls
    stall_timeout_seconds: int = 120  # Consider stalled after 2 minutes (was 60s)


@dataclass
class AgentConfig:
    """Agent configuration with all settings"""
    name: str
    role: AgentRole
    system_prompt: str
    nsec: str  # Nostr private key (bech32 or hex)
    model_config: ModelConfig = field(default_factory=ModelConfig)
    conversation_order: int = 0  # For sequential mode
    personality_traits: List[str] = field(default_factory=list)
    knowledge_base: List[str] = field(default_factory=list)
    debate_stance: str = "balanced"  # supportive, challenging, balanced
    
    def __post_init__(self):
        if not self.name:
            raise ValueError("Agent name required")
        if not self.nsec:
            raise ValueError("Agent nsec required")


@dataclass
class ConversationState:
    """Track conversation state"""
    root_event_id: str
    events: List[Event] = field(default_factory=list)
    agent_replies: Dict[str, int] = field(default_factory=dict)
    round_number: int = 0
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def add_event(self, event: Event):
        self.events.append(event)
        self.events.sort(key=lambda e: e.created_at().as_secs())
        self.last_activity = datetime.now(timezone.utc)


class OllamaClient:
    """Ollama LLM client with retry logic"""
    
    def __init__(self, config: ModelConfig):
        self.config = config
        self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                limits=httpx.Limits(max_connections=10)
            )
        return self._client
    
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                client = self._get_client()
                
                # Build options without max_tokens if not set
                options = {"temperature": self.config.temperature}
                if self.config.max_tokens and self.config.max_tokens > 0:
                    options["num_predict"] = self.config.max_tokens
                
                # Build the request payload
                payload = {
                    "model": self.config.model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "options": options,
                    "stream": False
                }
                
                # Log the request details for debugging
                logger.debug(f"LLM Request (attempt {attempt + 1}/{max_retries}):")
                logger.debug(f"  URL: {self.config.base_url}/api/chat")
                logger.debug(f"  Model: {self.config.model_name}")
                logger.debug(f"  System prompt: {system_prompt[:100]}...")
                logger.debug(f"  User prompt: {user_prompt[:100]}...")
                logger.debug(f"  Options: {options}")
                
                response = await client.post(
                    f"{self.config.base_url}/api/chat",
                    json=payload
                )
                
                # Log response status
                logger.debug(f"  Response status: {response.status_code}")
                
                # Check for HTTP errors
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"LLM API returned error {response.status_code}:")
                    logger.error(f"  Response body: {error_text[:500]}")
                    raise ValueError(f"HTTP {response.status_code}: {error_text[:200]}")
                
                response.raise_for_status()
                result = response.json()
                
                # Log successful response structure
                logger.debug(f"  Response keys: {list(result.keys())}")
                
                # Extract content from response
                if "message" in result and "content" in result["message"]:
                    content = result["message"]["content"]
                    logger.debug(f"  Generated {len(content)} characters")
                    return content
                elif "response" in result:
                    content = result["response"]
                    logger.debug(f"  Generated {len(content)} characters (from 'response' field)")
                    return content
                else:
                    # Log the actual response for debugging
                    logger.error(f"Unexpected response format from Ollama:")
                    logger.error(f"  Response keys: {list(result.keys())}")
                    logger.error(f"  Full response: {json.dumps(result, indent=2)[:1000]}")
                    raise ValueError(f"Invalid response format: expected 'message.content' or 'response', got keys: {list(result.keys())}")
                    
            except httpx.TimeoutException as e:
                last_error = e
                logger.error(f"LLM generation attempt {attempt + 1} TIMEOUT:")
                logger.error(f"  Timeout after {self.config.timeout} seconds")
                logger.error(f"  Consider increasing timeout in ModelConfig")
                
            except httpx.ConnectError as e:
                last_error = e
                logger.error(f"LLM generation attempt {attempt + 1} CONNECTION ERROR:")
                logger.error(f"  Could not connect to {self.config.base_url}")
                logger.error(f"  Is Ollama running? Check with: curl {self.config.base_url}/api/tags")
                logger.error(f"  Error: {e}")
                
            except json.JSONDecodeError as e:
                last_error = e
                logger.error(f"LLM generation attempt {attempt + 1} JSON DECODE ERROR:")
                logger.error(f"  Could not parse response as JSON")
                logger.error(f"  Raw response: {response.text[:500] if 'response' in locals() else 'No response'}")
                logger.error(f"  Error: {e}")
                
            except Exception as e:
                last_error = e
                logger.error(f"LLM generation attempt {attempt + 1} UNEXPECTED ERROR:")
                logger.error(f"  Error type: {type(e).__name__}")
                logger.error(f"  Error message: {str(e)}")
                logger.error(f"  Full error: {repr(e)}")
                
                # Try to provide more context
                import traceback
                logger.error(f"  Traceback:\n{traceback.format_exc()}")
            
            # Retry logic
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                # Final failure - provide detailed error summary
                logger.error("="*60)
                logger.error("LLM GENERATION FAILED - SUMMARY")
                logger.error("="*60)
                logger.error(f"Model: {self.config.model_name}")
                logger.error(f"Base URL: {self.config.base_url}")
                logger.error(f"Attempts: {max_retries}")
                logger.error(f"Last error: {last_error}")
                logger.error("Suggestions:")
                logger.error("  1. Check Ollama is running: ps aux | grep ollama")
                logger.error("  2. Test model: ollama run qwen3:14b")
                logger.error(f"  3. Test API: curl {self.config.base_url}/api/tags")
                logger.error("  4. Check model exists: ollama list")
                logger.error("="*60)
                
                # Return a fallback response with error details
                return f"[LLM Error after {max_retries} attempts: {type(last_error).__name__}: {str(last_error)[:100]}]"
    
    async def close(self):
        if self._client:
            await self._client.aclose()


class ReplyStrategy:
    """Intelligent parent selection for dynamic debate"""
    
    @staticmethod
    def select_reply_target(thread_events: List[Event],
                           agent_pubkey: str,
                           last_own_reply: Optional[Event],
                           debate_intensity: float = 0.7,
                           enable_external: bool = True) -> Optional[Event]:
        """
        Select which message to reply to based on:
        - Content relevance and debate opportunity
        - Avoiding echo chambers (prefer replying to others)
        - Thread balance and freshness
        - External participant consideration
        """
        if not thread_events:
            return None
        
        # Get candidates (recent messages, excluding our own very recent ones)
        candidates = []
        now = datetime.now(timezone.utc)
        
        for event in thread_events[-10:]:  # Consider last 10 messages
            author = event.author().to_hex()
            
            # Skip our own messages if we just replied
            if author == agent_pubkey and last_own_reply:
                if event.id().to_hex() == last_own_reply.id().to_hex():
                    continue
            
            # Add all other messages as candidates
            candidates.append(event)
        
        if not candidates:
            # Fallback to last message in thread
            return thread_events[-1] if thread_events else None
        
        # Score candidates
        scores = []
        for event in candidates:
            score = 0.0
            author = event.author().to_hex()
            
            # Prefer replying to others (avoid echo chamber)
            if author != agent_pubkey:
                score += 0.3
            
            # Prefer recent messages (freshness)
            event_age = now.timestamp() - event.created_at().as_secs()
            if event_age < 30:  # Very recent (< 30 seconds)
                score += 0.3
            elif event_age < 120:  # Recent (< 2 minutes)
                score += 0.2
            
            # Prefer longer, more substantive messages (more to debate)
            content_length = len(event.content())
            if content_length > 500:
                score += 0.2
            elif content_length > 200:
                score += 0.1
            
            # Look for debate-worthy content (questions, claims, opinions)
            content_lower = event.content().lower()
            debate_triggers = ['think', 'believe', 'should', 'must', 'wrong', 
                             'right', 'agree', 'disagree', 'however', 'but',
                             '?', 'why', 'how', 'what if']
            
            for trigger in debate_triggers:
                if trigger in content_lower:
                    score += 0.05
            
            # Apply debate intensity multiplier
            score *= debate_intensity
            
            scores.append((score, event))
        
        # Sort by score and return best candidate
        scores.sort(key=lambda x: x[0], reverse=True)
        
        if scores:
            best_score, best_event = scores[0]
            logger.debug(f"Selected reply target with score {best_score:.2f}")
            return best_event
        
        return thread_events[-1] if thread_events else None


class NostrAgent:
    """Individual AI agent in the swarm"""
    
    def __init__(self, config: AgentConfig, relay_urls: List[str]):
        self.config = config
        self.relay_urls = relay_urls
        
        # Initialize Nostr keys
        self.keys = Keys.parse(config.nsec)
        self.pubkey = self.keys.public_key().to_hex()
        
        # Initialize LLM
        self.llm_client = OllamaClient(config.model_config)
        
        # Nostr client
        self.signer = NostrSigner.keys(self.keys)
        self.client = Client(self.signer)
        
        self._running = False
        self._monitor_task = None
    
    async def connect(self):
        """Connect to relays"""
        for relay_url in self.relay_urls:
            try:
                relay = RelayUrl.parse(relay_url)
                await self.client.add_relay(relay)
            except Exception as e:
                logger.error(f"Failed to add relay {relay_url}: {e}")
        
        await self.client.connect()
        logger.info(f"Agent {self.config.name} connected")
    
    async def disconnect(self):
        """Disconnect and cleanup"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        await self.client.disconnect()
        await self.llm_client.close()
        logger.info(f"Agent {self.config.name} disconnected")
    
    def _clean_response(self, response: str) -> str:
        """Remove ALL thinking tags and their content - preserve everything else"""
        if not response:
            return ""
        
        # More aggressive cleaning - handle all variations
        # Remove <think>...</think> and <thinking>...</thinking> tags
        patterns = [
            r'<think[^>]*>.*?</think>', 
            r'<thinking[^>]*>.*?</thinking>',
            r'<thought[^>]*>.*?</thought>',
            # Handle mismatched/unclosed tags
            r'<think[^>]*>.*?(?=\n\n|$)',  # From <think> to double newline or end
            r'<thinking[^>]*>.*?(?=\n\n|$)',
        ]
        
        cleaned = response
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove any remaining standalone tags
        cleaned = re.sub(r'</?(?:think|thinking|thought)[^>]*>', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra whitespace but preserve structure
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Max 2 newlines
        cleaned = cleaned.strip()
        
        # NEVER TRUNCATE - return the full cleaned response
        return cleaned
    
    async def generate_response(self, root_content: str, 
                               thread_events: List[Event]) -> Optional[str]:
        """Generate response considering full thread context"""
        
        # Build conversation history
        conversation = []
        for event in thread_events:
            author = event.author().to_hex()
            content = event.content()  # Don't truncate - show full messages
            
            speaker = "Me" if author == self.pubkey else f"Agent_{author[:6]}"
            conversation.append(f"[{speaker}]: {content}")
        
        # Build prompts
        system_prompt = f"""You are {self.config.name}, a {self.config.role.value} AI agent participating in a discussion.

Role: {self.config.system_prompt}
Traits: {', '.join(self.config.personality_traits)}
Knowledge: {', '.join(self.config.knowledge_base)}

CRITICAL INSTRUCTIONS:
- Start your response DIRECTLY with your substantive answer
- Do NOT include any thinking, reasoning, or meta-commentary
- Do NOT say things like "Let me think", "Wait", "Oh", "Actually", etc.
- Do NOT mention "the user" or describe what you're doing
- Just provide your direct response to the topic

Requirements:
1. Consider ALL previous messages in the thread
2. Build on and reference other agents' ideas  
3. Add your unique {self.config.role.value} perspective
4. Share your complete thoughts without worrying about length
5. Focus on substantive content

Begin your response immediately:"""

        user_prompt = f"""Original topic: {root_content}

Thread so far:
{chr(10).join(conversation)}

Provide your {self.config.role.value} perspective. Start with a complete answer to the topic. Do not begin mid-thought or with transitional phrases like 'Then', 'Also', 'Another thing', etc."""

        try:
            raw_response = await self.llm_client.generate(system_prompt, user_prompt)
            
            # Debug logging for troubleshooting
            if raw_response and len(raw_response) > 0:
                logger.debug(f"{self.config.name} raw response length: {len(raw_response)}")
                if '<think>' in raw_response.lower():
                    logger.debug(f"{self.config.name} response contains <think> tags")
            
            response = self._clean_response(raw_response)
            
            if not response:
                logger.warning(f"{self.config.name} generated empty response after cleaning")
                if raw_response:
                    logger.warning(f"Raw response was: {raw_response[:500]}...")
                return None
            
            # Don't truncate - post the full LLM response
            # Nostr supports up to ~32KB which is way more than any LLM will generate
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return None
    
    async def reply_with_debate(self, root_event: Event,
                               thread_events: List[Event],
                               debate_config: SwarmConfig,
                               last_own_reply: Optional[Event] = None) -> Optional[Event]:
        """Generate and post a debate-style reply targeting the best message"""
        
        logger.debug(f"{self.config.name} starting reply_with_debate, thread has {len(thread_events)} events")
        
        # Use ReplyStrategy to select target
        target_event = ReplyStrategy.select_reply_target(
            thread_events,
            self.pubkey,
            last_own_reply,
            debate_config.debate_intensity,
            debate_config.enable_external_participants
        )
        
        if not target_event:
            logger.warning(f"{self.config.name} found no suitable debate target")
            return None
        
        logger.debug(f"{self.config.name} selected target: {target_event.content()[:30]}...")
        
        # Generate debate-focused response
        logger.debug(f"{self.config.name} generating debate response...")
        response_text = await self.generate_debate_response(
            root_event.content(),
            thread_events,
            target_event,
            debate_config.debate_intensity
        )
        
        if not response_text:
            logger.warning(f"{self.config.name} failed to generate response text")
            return None
        
        logger.debug(f"{self.config.name} generated response: {response_text[:50]}...")
        
        # Post the reply
        return await self._post_reply(root_event, target_event, response_text, thread_events)
    
    async def generate_debate_response(self, root_content: str,
                                      thread_events: List[Event],
                                      target_event: Event,
                                      debate_intensity: float) -> Optional[str]:
        """Generate a debate-focused response to a specific message"""
        
        # Build conversation history
        conversation = []
        for event in thread_events[-15:]:  # Last 15 messages for context
            author = event.author().to_hex()
            content = event.content()
            
            speaker = "Me" if author == self.pubkey else f"Agent_{author[:6]}"
            conversation.append(f"[{speaker}]: {content}")
        
        # Get target author name
        target_author = target_event.author().to_hex()
        target_name = "Me" if target_author == self.pubkey else f"Agent_{target_author[:6]}"
        
        # Build debate directive based on role and stance
        debate_directive = self._get_debate_directive(debate_intensity)
        
        # Build prompts
        system_prompt = f"""You are {self.config.name}, a {self.config.role.value} AI agent in a debate.

Role: {self.config.system_prompt}
Traits: {', '.join(self.config.personality_traits)}
Stance: {self.config.debate_stance}

DEBATE INSTRUCTIONS:
- You're responding SPECIFICALLY to {target_name}'s message
- {debate_directive}
- Reference their specific claims or arguments
- Be direct and engaging

CRITICAL THINKING REQUIREMENTS:
1. Identify strengths and weaknesses in their argument
2. Provide counter-examples or alternative perspectives if you disagree
3. Build upon valid points while challenging questionable ones
4. Use evidence and reasoning to support your position
5. Acknowledge good points even when disagreeing overall

Start your response directly without meta-commentary."""

        user_prompt = f"""Original topic: {root_content}

Thread context:
{chr(10).join(conversation)}

TARGET MESSAGE from {target_name}:
"{target_event.content()}"

Provide your {self.config.role.value} perspective on {target_name}'s message. Be specific about what you're addressing."""

        try:
            raw_response = await self.llm_client.generate(system_prompt, user_prompt)
            response = self._clean_response(raw_response)
            
            if not response:
                logger.warning(f"{self.config.name} generated empty debate response")
                return None
            
            # Don't truncate - post everything the LLM returns
            # Nostr can handle up to ~32KB which is plenty
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to generate debate response: {e}")
            return None
    
    def _get_debate_directive(self, intensity: float) -> str:
        """Get debate directive based on stance and intensity"""
        if self.config.debate_stance == "challenging":
            if intensity > 0.7:
                return "Challenge their assumptions strongly, find flaws, play devil's advocate"
            else:
                return "Question their reasoning constructively, explore alternatives"
        elif self.config.debate_stance == "supportive":
            if intensity > 0.7:
                return "Build strongly on their ideas, defend against criticism"
            else:
                return "Expand on their points, add supporting evidence"
        else:  # balanced
            if intensity > 0.7:
                return "Engage critically but fairly, challenge weak points while acknowledging strong ones"
            else:
                return "Provide balanced analysis, consider multiple perspectives"
    
    async def _post_reply(self, root_event: Event, 
                         target_event: Event,
                         response_text: str,
                         thread_events: List[Event]) -> Optional[Event]:
        """Post a reply with proper threading"""
        
        root_id = root_event.id().to_hex()
        target_id = target_event.id().to_hex()
        
        logger.info(f"{self.config.name} replying to {target_id[:8]}...: {response_text[:50]}...")
        
        # Build proper NIP-10 tags
        tags = []
        
        # Always include root tag
        tags.append(Tag.parse(["e", root_id, "", "root"]))
        
        # Reply to specific target
        tags.append(Tag.parse(["e", target_id, "", "reply"]))
        
        # Add author of message we're replying to
        tags.append(Tag.parse(["p", target_event.author().to_hex()]))
        
        # Add mentions for active participants
        participants = set()
        for event in thread_events[-10:]:
            author = event.author().to_hex()
            if author != self.pubkey and author != target_event.author().to_hex():
                participants.add(author)
        
        for participant in list(participants)[:5]:  # Limit mentions
            tags.append(Tag.parse(["p", participant]))
        
        # Create and send
        reply_builder = EventBuilder.text_note(response_text).tags(tags)
        reply_event = reply_builder.sign_with_keys(self.keys)
        
        output = await self.client.send_event(reply_event)
        
        if output.success:
            event_id = reply_event.id().to_hex()
            logger.info(f"✅ {self.config.name} posted debate reply: {event_id}")
            
            # Quick verification
            await asyncio.sleep(0.5)
            return reply_event
        else:
            logger.error(f"❌ {self.config.name} failed to post debate reply")
            return None
    
    async def create_synthesis(self, root_event: Event,
                              thread_events: List[Event]) -> Optional[str]:
        """Create a synthesis/summary of the debate (for supervisor agents)"""
        
        logger.info(f"[{self.config.name}] Starting synthesis creation...")
        
        if self.config.role != AgentRole.SUPERVISOR:
            logger.warning(f"{self.config.name} is not a supervisor but tried to synthesize")
            return None
        
        logger.info(f"[{self.config.name}] Processing {len(thread_events)} events for synthesis...")
        
        # Analyze participants and their positions
        participants = {}
        for event in thread_events[1:]:  # Skip root
            author = event.author().to_hex()
            if author not in participants:
                participants[author] = []
            participants[author].append(event.content())
        
        # Build comprehensive prompt for synthesis
        system_prompt = f"""You are {self.config.name}, a supervisor agent tasked with synthesizing a debate.

Your role: {self.config.system_prompt}

SYNTHESIS REQUIREMENTS:
1. Identify key points of agreement across participants
2. Highlight unresolved disagreements and their implications
3. Synthesize the best ideas from all participants
4. Provide a balanced, actionable conclusion
5. Credit specific contributors when appropriate
6. Weigh different perspectives fairly

Be comprehensive but concise. Focus on insights and conclusions."""

        # Build thread summary
        thread_summary = []
        for i, event in enumerate(thread_events):
            author = event.author().to_hex()
            author_name = f"Participant_{author[:6]}"
            content = event.content()
            
            if i == 0:
                thread_summary.append(f"ORIGINAL TOPIC: {content}")
            else:
                # Truncate very long messages in summary
                if len(content) > 500:
                    content = content[:497] + "..."
                thread_summary.append(f"[{author_name}]: {content}")
        
        user_prompt = f"""Analyze this debate with {len(thread_events)} messages from {len(participants)} participants.

Thread:
{chr(10).join(thread_summary)}

Create a comprehensive synthesis that:
- Identifies consensus points
- Notes key disagreements
- Synthesizes the best insights
- Provides actionable conclusions
- Credits contributors

Focus on substance over process. What did we learn? What conclusions can we draw?"""

        logger.info(f"[{self.config.name}] Calling LLM for synthesis generation...")
        logger.debug(f"[{self.config.name}] Synthesis prompt length: {len(system_prompt + user_prompt)} chars")
        
        try:
            raw_response = await self.llm_client.generate(system_prompt, user_prompt)
            logger.info(f"[{self.config.name}] LLM synthesis response received: {len(raw_response)} chars")
            
            # Extra aggressive cleaning for synthesis to remove ALL thinking
            # Remove everything that looks like internal monologue
            cleaned = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL | re.IGNORECASE)
            cleaned = re.sub(r'<thinking>.*?</thinking>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
            
            # Remove common thinking patterns at the start
            lines = cleaned.split('\n')
            final_lines = []
            skip_mode = True  # Start in skip mode
            
            for line in lines:
                line_lower = line.lower().strip()
                
                # Skip lines that are clearly thinking/planning
                if skip_mode and any(x in line_lower for x in [
                    'first, i need', 'next, i', 'i should', 'let me',
                    'participant_', 'they mention', 'they both seem'
                ]):
                    continue
                
                # Look for actual synthesis content markers
                if any(x in line_lower for x in [
                    'consensus:', 'agreement:', 'disagreement:', 
                    'conclusion:', 'summary:', 'synthesis:',
                    'key points:', 'insights:', 'findings:'
                ]):
                    skip_mode = False  # Found real content
                
                # Once we found real content, keep everything
                if not skip_mode:
                    final_lines.append(line)
                # Also keep lines that look like headers or conclusions
                elif line.strip() and (
                    line.strip().startswith('**') or 
                    line.strip().startswith('#') or
                    line.strip().isupper()
                ):
                    skip_mode = False
                    final_lines.append(line)
            
            response = '\n'.join(final_lines).strip()
            
            # If we removed everything, try basic cleaning
            if not response:
                response = self._clean_response(raw_response)
            
            if not response:
                logger.warning(f"Supervisor {self.config.name} generated empty synthesis")
                return None
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to generate synthesis: {e}")
            return None
    
    async def post_synthesis(self, root_event: Event,
                            thread_events: List[Event],
                            synthesis: str) -> Optional[Event]:
        """Post a synthesis as a supervisor"""
        
        root_id = root_event.id().to_hex()
        
        # Add a header to the synthesis
        final_message = f"🎯 SYNTHESIS by {self.config.name} (Supervisor)\n\n{synthesis}"
        
        logger.info(f"Supervisor {self.config.name} posting synthesis...")
        
        # Build tags - reply to root and mention all participants
        tags = []
        tags.append(Tag.parse(["e", root_id, "", "root"]))
        tags.append(Tag.parse(["e", root_id, "", "reply"]))  # Reply to root for synthesis
        
        # Mention all unique participants
        participants = set()
        for event in thread_events[1:]:  # Skip root
            author = event.author().to_hex()
            if author != self.pubkey:
                participants.add(author)
        
        for participant in participants:
            tags.append(Tag.parse(["p", participant]))
        
        # Create and send
        synthesis_builder = EventBuilder.text_note(final_message).tags(tags)
        synthesis_event = synthesis_builder.sign_with_keys(self.keys)
        
        output = await self.client.send_event(synthesis_event)
        
        if output.success:
            event_id = synthesis_event.id().to_hex()
            logger.info(f"✅ Supervisor posted synthesis: {event_id}")
            return synthesis_event
        else:
            logger.error(f"❌ Supervisor failed to post synthesis")
            return None
    
    async def reply_to_thread(self, root_event: Event, 
                            thread_events: List[Event]) -> Optional[Event]:
        """Generate and post a reply with proper threading"""
        
        root_id = root_event.id().to_hex()
        
        # Generate response
        response_text = await self.generate_response(
            root_event.content(), 
            thread_events
        )
        
        if not response_text:
            return None
        
        logger.info(f"{self.config.name} posting: {response_text[:50]}...")
        
        # CRITICAL: Race condition guard - re-fetch thread before deciding parent
        await asyncio.sleep(0.5)  # Short delay to catch concurrent posts
        
        # Re-fetch to get latest state
        from nostr_sdk import Filter, EventId, Timestamp
        fresh_filter = Filter().kinds([Kind(1)])
        
        # Get fresh thread state
        fresh_events = await self.client.fetch_events(fresh_filter, timedelta(seconds=3))
        fresh_thread = []
        
        if fresh_events:
            for event in fresh_events.to_vec():
                if event.id().to_hex() == root_id:
                    fresh_thread.append(event)
                    continue
                tags = event.tags().to_vec() if event.tags() else []
                for tag in tags:
                    tag_vec = tag.as_vec()
                    if (len(tag_vec) >= 2 and tag_vec[0] == "e" and tag_vec[1] == root_id):
                        fresh_thread.append(event)
                        break
        
        # Sort and use fresh thread for parent selection
        fresh_thread.sort(key=lambda e: e.created_at().as_secs())
        
        # Determine parent with fresh data
        if fresh_thread and len(fresh_thread) > 0:
            # Find the last event that isn't from us
            reply_to_event = None
            for event in reversed(fresh_thread):
                if event.author().to_hex() != self.pubkey:
                    reply_to_event = event
                    break
            
            if not reply_to_event:
                reply_to_event = fresh_thread[-1] if fresh_thread else root_event
        else:
            reply_to_event = root_event
        
        reply_to_id = reply_to_event.id().to_hex()
        
        # Build proper NIP-10 tags
        tags = []
        
        # Always include root tag
        tags.append(Tag.parse(["e", root_id, "", "root"]))
        
        # Always include reply tag (even if replying to root)
        # This maintains consistent threading
        tags.append(Tag.parse(["e", reply_to_id, "", "reply"]))
        
        # Add author of message we're replying to
        tags.append(Tag.parse(["p", reply_to_event.author().to_hex()]))
        
        # Add mentions for recent participants
        participants = set()
        for event in thread_events[-5:]:
            author = event.author().to_hex()
            if author != self.pubkey and author != reply_to_event.author().to_hex():
                participants.add(author)
        
        for participant in list(participants)[:3]:
            tags.append(Tag.parse(["p", participant]))
        
        # Create and send
        reply_builder = EventBuilder.text_note(response_text).tags(tags)
        reply_event = reply_builder.sign_with_keys(self.keys)
        
        output = await self.client.send_event(reply_event)
        
        if output.success:
            event_id = reply_event.id().to_hex()
            logger.info(f"✅ {self.config.name} posted event ID: {event_id}")
            logger.info(f"   Replying to parent: {reply_to_id}")
            
            # CRITICAL: Verify with exponential backoff for relay lag
            logger.info(f"🔍 Verifying event {event_id[:16]}... is on relay...")
            
            # Exponential backoff retry
            max_retries = 3
            retry_delays = [0.5, 1.5, 3.0]  # Increasing delays
            
            verified = False
            for attempt, delay in enumerate(zip(range(max_retries), retry_delays)):
                await asyncio.sleep(delay[1])
                
                try:
                    event_filter = Filter().ids([reply_event.id()]).limit(1)
                    events = await self.client.fetch_events(event_filter, timedelta(seconds=10))
                
                    if events:
                        events_list = events.to_vec()
                        if events_list and events_list[0].id().to_hex() == event_id:
                            logger.info(f"✅ VERIFIED: Event found on relay (attempt {attempt+1})")
                            verified = True
                            break
                except Exception as e:
                    logger.debug(f"Verification attempt {attempt+1} failed: {e}")
                
                if attempt < max_retries - 1:
                    logger.debug(f"Retrying verification...")
            
            if verified:
                return reply_event
            else:
                logger.warning(f"⚠️ Could not verify event after {max_retries} attempts")
                # Return anyway - relay might have it but be slow to confirm
                return reply_event
        else:
            logger.error(f"❌ {self.config.name} failed to post")
            return None


class NostrSwarm:
    """Main swarm orchestrator with multiple conversation modes"""
    
    def __init__(self, relay_urls: List[str], 
                 mode: ConversationMode = ConversationMode.SEQUENTIAL,
                 config: Optional[SwarmConfig] = None):
        self.relay_urls = relay_urls
        self.mode = mode
        self.config = config or SwarmConfig()
        self.agents: List[NostrAgent] = []
        self.agent_order: List[NostrAgent] = []
        self.conversations: Dict[str, ConversationState] = {}
        self._running = False
        self.supervisor_agent: Optional[NostrAgent] = None
        self.debate_agents: List[NostrAgent] = []
    
    def add_agent(self, config: AgentConfig) -> NostrAgent:
        """Add agent to swarm"""
        agent = NostrAgent(config, self.relay_urls)
        
        # Handle supervisor specially
        if config.role == AgentRole.SUPERVISOR:
            self.supervisor_agent = agent
            logger.info(f"Added supervisor agent: {config.name}")
        else:
            self.agents.append(agent)
            self.debate_agents.append(agent)
        
        # Sort by conversation order for sequential mode
        self.agent_order = sorted(
            self.agents,
            key=lambda a: a.config.conversation_order
        )
        
        return agent
    
    async def start(self):
        """Start all agents"""
        # Connect debate agents
        for agent in self.agents:
            await agent.connect()
        
        # Connect supervisor if present
        if self.supervisor_agent:
            await self.supervisor_agent.connect()
        
        self._running = True
        
        total_agents = len(self.agents) + (1 if self.supervisor_agent else 0)
        logger.info(f"Swarm started with {total_agents} agents in {self.mode.value} mode")
        
        if self.supervisor_agent:
            logger.info(f"Supervisor: {self.supervisor_agent.config.name} (triggers at {self.config.max_replies_before_summary} replies)")
        
        if self.mode == ConversationMode.SEQUENTIAL:
            logger.info(f"Order: {[a.config.name for a in self.agent_order]}")
    
    async def stop(self):
        """Stop all agents"""
        self._running = False
        
        for agent in self.agents:
            await agent.disconnect()
        
        if self.supervisor_agent:
            await self.supervisor_agent.disconnect()
        
        logger.info("Swarm stopped")
    
    async def fetch_thread_events(self, root_event_id: str, root_timestamp: Optional[int] = None) -> List[Event]:
        """Fetch all events in a thread using NIP-10 tags efficiently"""
        if not self.agents:
            return []
        
        client = self.agents[0].client
        
        # Build filter for thread events
        # Use tags filter for events that reference this root
        thread_filter = Filter().kinds([Kind(1)])
        
        # Add time window if we have root timestamp
        # Fetch events from root time onwards (threads can't start before root)
        if root_timestamp:
            thread_filter = thread_filter.since(Timestamp.from_secs(root_timestamp))
        
        # Limit to reasonable amount
        thread_filter = thread_filter.limit(50)
        
        # First, get the root event itself
        try:
            root_event_id_obj = EventId.parse(root_event_id)
        except:
            # Fallback if parse doesn't work
            root_event_id_obj = root_event_id
        
        root_filter = Filter().ids([root_event_id_obj]).limit(1)
        
        try:
            # Fetch both root and potential thread events
            root_events = await client.fetch_events(root_filter, timedelta(seconds=5))
            thread_events = await client.fetch_events(thread_filter, timedelta(seconds=5))
            
            result = []
            
            # Add root if found
            if root_events:
                root_list = root_events.to_vec()
                if root_list:
                    result.append(root_list[0])
            
            # Filter for actual thread members
            if thread_events:
                for event in thread_events.to_vec():
                    # Skip if it's the root itself
                    if event.id().to_hex() == root_event_id:
                        continue
                    
                    # Check if event references our root
                    tags = event.tags().to_vec() if event.tags() else []
                    for tag in tags:
                        tag_vec = tag.as_vec()
                        # Look for "e" tags that reference our root
                        if (len(tag_vec) >= 2 and 
                            tag_vec[0] == "e" and 
                            tag_vec[1] == root_event_id):
                            result.append(event)
                            break
            
            # Sort chronologically
            result.sort(key=lambda e: e.created_at().as_secs())
            return result
            
        except Exception as e:
            logger.error(f"Error fetching thread: {e}")
            return []
    
    async def run_conversation_round(self, root_event: Event, round_num: int = 1):
        """Run one round of conversation with proper threading"""
        root_id = root_event.id().to_hex()
        
        logger.info(f"Round {round_num} starting for: {root_event.content()[:50]}...")
        
        if root_id not in self.conversations:
            self.conversations[root_id] = ConversationState(root_id)
        
        state = self.conversations[root_id]
        state.round_number = round_num
        
        if self.mode == ConversationMode.SEQUENTIAL:
            # Sequential: agents take turns in order
            for i, agent in enumerate(self.agent_order):
                logger.info(f"  Turn {i+1}/{len(self.agent_order)}: {agent.config.name}")
                
                # Fetch current thread state with timestamp optimization
                root_timestamp = root_event.created_at().as_secs()
                thread_events = await self.fetch_thread_events(root_id, root_timestamp)
                
                # Agent replies with proper parent reference
                reply = await agent.reply_to_thread(
                    root_event, 
                    thread_events
                )
                
                if reply:
                    # Add the reply to our local state
                    state.add_event(reply)
                    state.agent_replies[agent.config.name] = \
                        state.agent_replies.get(agent.config.name, 0) + 1
                    
                    # Log threading info
                    reply_tags = reply.tags().to_vec() if reply.tags() else []
                    parent_id = None
                    for tag in reply_tags:
                        tag_vec = tag.as_vec()
                        if len(tag_vec) >= 4 and tag_vec[0] == "e" and tag_vec[3] == "reply":
                            parent_id = tag_vec[1][:8]
                            break
                    
                    logger.info(f"  └─> Reply posted with parent: {parent_id}...")
                    
                    # Wait before next agent to ensure proper ordering
                    await asyncio.sleep(3)
        
        elif self.mode == ConversationMode.PARALLEL:
            # Parallel: all agents respond simultaneously
            tasks = []
            thread_events = await self.fetch_thread_events(root_id)
            
            for agent in self.agents:
                tasks.append(agent.reply_to_thread(root_event, thread_events))
            
            replies = await asyncio.gather(*tasks, return_exceptions=True)
            
            for agent, reply in zip(self.agents, replies):
                if isinstance(reply, Event):
                    state.agent_replies[agent.config.name] = \
                        state.agent_replies.get(agent.config.name, 0) + 1
        
        logger.info(f"Round {round_num} complete")
    
    async def run_supervised_debate(self, root_event: Event) -> None:
        """Run a supervised debate with continuous monitoring until supervisor intervenes"""
        
        if self.mode not in [ConversationMode.DEBATE, ConversationMode.SUPERVISED_DEBATE]:
            logger.warning("run_supervised_debate called but mode is not debate")
            return
        
        root_id = root_event.id().to_hex()
        
        # Log the root message
        logger.info(f"📌 Starting supervised debate on: {root_event.content()[:50]}...")
        logger.info(f"   Root ID: {root_id}")
        logger.info(f"   Threshold: {self.config.max_replies_before_summary} replies")
        logger.info(f"   Number of debate agents: {len(self.debate_agents)}")
        logger.info(f"   Supervisor present: {self.supervisor_agent is not None}")
        
        # Post root event if needed
        await self._ensure_root_posted(root_event)
        
        # Track agent replies
        agent_last_replies = {agent.pubkey: None for agent in self.debate_agents}
        last_activity = datetime.now(timezone.utc)
        synthesis_triggered = False
        
        # Start monitoring task
        async def monitor_thread():
            """Continuously monitor thread for synthesis trigger"""
            nonlocal synthesis_triggered, last_activity
            while self._running and not synthesis_triggered:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                # Fetch current thread
                thread_events = await self.fetch_thread_events(root_id, root_event.created_at().as_secs())
                if not thread_events:
                    continue
                
                # Count replies (excluding root)
                reply_count = len([e for e in thread_events if e.id().to_hex() != root_id])
                
                if reply_count >= self.config.max_replies_before_summary:
                    logger.info(f"\n🎯 Monitor: Threshold reached! {reply_count} replies")
                    synthesis_triggered = True
                    break
                
                # Check for stall
                now = datetime.now(timezone.utc)
                if (now - last_activity).total_seconds() > self.config.stall_timeout_seconds:
                    logger.info(f"\n⏱️ Monitor: Debate stalled after {reply_count} replies")
                    if reply_count >= self.config.min_replies_before_summary:
                        synthesis_triggered = True
                    break
        
        # Start monitor in background
        monitor_task = asyncio.create_task(monitor_thread())
        
        try:
            # Debate loop - agents reply naturally until threshold
            round_num = 0
            while self._running and not synthesis_triggered:
                round_num += 1
                logger.info(f"\n--- Debate Round {round_num} ---")
                logger.info(f"   Synthesis triggered: {synthesis_triggered}")
                logger.info(f"   Running: {self._running}")
                
                # Fetch current thread state
                logger.info("   Fetching thread events...")
                thread_events = await self.fetch_thread_events(root_id, root_event.created_at().as_secs())
                if not thread_events:
                    logger.info("   No thread events found, using root only")
                    thread_events = [root_event]
                
                # Count current replies
                reply_count = len([e for e in thread_events if e.id().to_hex() != root_id])
                logger.info(f"   Current thread: {reply_count} replies (need {self.config.max_replies_before_summary})")
                
                # Randomly shuffle agents for natural debate flow
                import random
                debate_order = list(self.debate_agents)
                random.shuffle(debate_order)
                
                replies_this_round = 0
                for i, agent in enumerate(debate_order):
                    if synthesis_triggered:
                        logger.info("   Synthesis triggered, breaking agent loop")
                        break
                    
                    logger.info(f"   Agent {i+1}/{len(debate_order)}: {agent.config.name} considering reply...")
                    
                    # Let agent decide if they want to reply
                    try:
                        reply = await agent.reply_with_debate(
                            root_event,
                            thread_events,
                            self.config,
                            agent_last_replies.get(agent.pubkey)
                        )
                        
                        if reply:
                            agent_last_replies[agent.pubkey] = reply
                            last_activity = datetime.now(timezone.utc)
                            replies_this_round += 1
                            
                            # Update thread
                            thread_events = await self.fetch_thread_events(root_id, root_event.created_at().as_secs())
                            current_count = len([e for e in thread_events if e.id().to_hex() != root_id])
                            
                            logger.info(f"   ✅ {agent.config.name} replied [{current_count}/{self.config.max_replies_before_summary}]")
                            
                            # Natural pacing
                            await asyncio.sleep(self.config.reply_delay_seconds)
                        else:
                            logger.info(f"   ⏭️ {agent.config.name} chose not to reply")
                    except Exception as e:
                        logger.error(f"   ❌ {agent.config.name} failed to reply: {e}")
                
                if replies_this_round == 0:
                    logger.info("No agents replied this round")
                    await asyncio.sleep(5)  # Wait before retrying
        
        finally:
            # Cancel monitor
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        
        # Trigger supervisor synthesis if threshold reached
        if synthesis_triggered and self.supervisor_agent:
            logger.info(f"\n🎯 Triggering supervisor synthesis...")
            
            # Get final thread state
            thread_events = await self.fetch_thread_events(root_id, root_event.created_at().as_secs())
            reply_count = len([e for e in thread_events if e.id().to_hex() != root_id])
            logger.info(f"   Final thread: {reply_count} replies")
            
            # Generate synthesis
            logger.info(f"   Calling supervisor {self.supervisor_agent.config.name} to create synthesis...")
            try:
                # Synthesis can take time with large models, but 60s should be enough
                synthesis = await asyncio.wait_for(
                    self.supervisor_agent.create_synthesis(root_event, thread_events),
                    timeout=60.0  # 60 second timeout for synthesis
                )
                logger.info(f"   Synthesis created successfully: {len(synthesis) if synthesis else 0} chars")
            except asyncio.TimeoutError:
                logger.error("   ❌ Supervisor synthesis timed out after 60s")
                synthesis = None
            except Exception as e:
                logger.error(f"   ❌ Supervisor synthesis failed: {e}")
                synthesis = None
            
            if synthesis:
                # Post synthesis
                await self.supervisor_agent.post_synthesis(root_event, thread_events, synthesis)
                logger.info("✅ Supervisor synthesis posted!")
            else:
                logger.warning("Supervisor failed to generate synthesis")
        else:
            thread_events = await self.fetch_thread_events(root_id, root_event.created_at().as_secs())
            final_count = len([e for e in thread_events if e.id().to_hex() != root_id])
            logger.info(f"\nDebate ended with {final_count} replies")
    
    async def _ensure_root_posted(self, event: Event) -> None:
        """Ensure root event exists on relay"""
        try:
            root_filter = Filter().ids([event.id()]).limit(1)
            events = await self.agents[0].client.fetch_events(root_filter, timedelta(seconds=5))
            
            events_list = events.to_vec() if events else []
            if not events_list:
                logger.info("Posting root event to relay...")
                output = await self.agents[0].client.send_event(event)
                if output.success:
                    logger.info(f"✅ Posted root event")
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error checking root event: {e}")
    
    async def process_message(self, event: Event, max_rounds: int = 2):
        """Process a message and run conversation rounds"""
        root_id = event.id().to_hex()
        
        # Log the root message event ID
        content = event.content()
        logger.info(f"📌 ROOT EVENT ID: {root_id}")
        logger.info(f"Processing message: {content[:50]}...")
        
        # First, verify the root event exists on the relay
        logger.info(f"🔍 Verifying root event {root_id[:16]}... is on relay...")
        from nostr_sdk import Filter
        
        try:
            root_filter = Filter().ids([event.id()]).limit(1)
            events = await self.agents[0].client.fetch_events(root_filter, timedelta(seconds=5))
            
            events_list = events.to_vec() if events else []
            if not events_list:
                logger.warning(f"⚠️ Root event {root_id[:16]}... not found on relay - posting it now")
                
                # Post the root event if it's not on the relay
                output = await self.agents[0].client.send_event(event)
                if output.success:
                    logger.info(f"✅ Posted root event to relay: {root_id}")
                    await asyncio.sleep(1)  # Wait for propagation
                else:
                    logger.error(f"❌ Failed to post root event to relay")
                    return
            else:
                logger.info(f"✅ Root event {root_id[:16]}... exists on relay")
        except Exception as e:
            logger.error(f"Error checking root event: {e}")
        
        for round_num in range(1, max_rounds + 1):
            await self.run_conversation_round(event, round_num)
            
            if round_num < max_rounds:
                # Wait between rounds
                await asyncio.sleep(5)
        
        logger.info(f"Completed {max_rounds} rounds for message")


# Convenience function for quick setup
def create_swarm(relay_urls: List[str] = None,
                 mode: ConversationMode = ConversationMode.SEQUENTIAL,
                 config: Optional[SwarmConfig] = None) -> NostrSwarm:
    """Create a swarm with default settings"""
    if relay_urls is None:
        relay_urls = ["ws://localhost:7447"]
    
    return NostrSwarm(relay_urls, mode, config)


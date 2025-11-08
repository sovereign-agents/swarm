// ============================================================================
// Nostr AI Swarm - Frontend Application
// ============================================================================

class SwarmApp {
    constructor() {
        this.ws = null;
        this.roles = [];
        this.scenarios = [];
        this.currentEditingRole = null;
        this.currentEditingScenario = null;
        this.swarmStatus = null;

        this.init();
    }

    async init() {
        this.setupTabs();
        this.setupModals();
        this.setupForms();
        await this.loadRoles();
        await this.loadScenarios();
        this.setupSwarmControl();
        this.updateSwarmStatus();
        this.connectWebSocket();

        // Refresh status every 3 seconds
        setInterval(() => this.updateSwarmStatus(), 3000);
    }

    // ========================================================================
    // Tab Management
    // ========================================================================

    setupTabs() {
        const tabButtons = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');

        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tabName = button.dataset.tab;

                // Update active tab button
                tabButtons.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');

                // Update active tab content
                tabContents.forEach(content => {
                    content.classList.remove('active');
                    if (content.id === tabName) {
                        content.classList.add('active');
                    }
                });
            });
        });
    }

    // ========================================================================
    // Modal Management
    // ========================================================================

    setupModals() {
        // Role modal
        const roleModal = document.getElementById('role-modal');
        const newRoleBtn = document.getElementById('new-role-btn');
        const roleCloseBtns = roleModal.querySelectorAll('.close-btn, .cancel-btn');

        newRoleBtn.addEventListener('click', () => this.openRoleModal());
        roleCloseBtns.forEach(btn => {
            btn.addEventListener('click', () => this.closeModal(roleModal));
        });

        // Scenario modal
        const scenarioModal = document.getElementById('scenario-modal');
        const newScenarioBtn = document.getElementById('new-scenario-btn');
        const scenarioCloseBtns = scenarioModal.querySelectorAll('.close-btn, .cancel-btn');

        newScenarioBtn.addEventListener('click', () => this.openScenarioModal());
        scenarioCloseBtns.forEach(btn => {
            btn.addEventListener('click', () => this.closeModal(scenarioModal));
        });

        // Close modals on outside click
        window.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                this.closeModal(e.target);
            }
        });
    }

    openModal(modal) {
        modal.classList.add('active');
    }

    closeModal(modal) {
        modal.classList.remove('active');
    }

    // ========================================================================
    // Forms
    // ========================================================================

    setupForms() {
        // Role form
        const roleForm = document.getElementById('role-form');
        roleForm.addEventListener('submit', (e) => this.handleRoleSave(e));

        // Scenario form
        const scenarioForm = document.getElementById('scenario-form');
        scenarioForm.addEventListener('submit', (e) => this.handleScenarioSave(e));

        // Add agent button
        const addAgentBtn = document.getElementById('add-agent-btn');
        addAgentBtn.addEventListener('click', () => this.addAgentToScenario());

        // Start swarm form
        const startSwarmForm = document.getElementById('start-swarm-form');
        startSwarmForm.addEventListener('submit', (e) => this.handleSwarmStart(e));

        // Stop button
        const stopBtn = document.getElementById('stop-btn');
        stopBtn.addEventListener('click', () => this.handleSwarmStop());
    }

    // ========================================================================
    // Roles Management
    // ========================================================================

    async loadRoles() {
        try {
            const response = await fetch('/api/roles');
            this.roles = await response.json();
            this.renderRoles();
        } catch (error) {
            console.error('Failed to load roles:', error);
            this.showError('Failed to load roles');
        }
    }

    renderRoles() {
        const rolesList = document.getElementById('roles-list');

        if (this.roles.length === 0) {
            rolesList.innerHTML = '<p class="no-messages">No roles available. Create your first role!</p>';
            return;
        }

        rolesList.innerHTML = this.roles.map(role => `
            <div class="item-card">
                <div class="item-header">
                    <div>
                        <div class="item-title">${this.escapeHtml(role.name)}</div>
                        <div class="item-meta">
                            <span class="badge">${role.role}</span>
                            <span class="badge">${role.debate_stance}</span>
                        </div>
                    </div>
                    <div class="item-actions">
                        <button class="btn btn-secondary btn-small" onclick="app.editRole('${role.id}')">Edit</button>
                        <button class="btn btn-danger btn-small" onclick="app.deleteRole('${role.id}')">Delete</button>
                    </div>
                </div>
                <div class="item-description">${this.escapeHtml(role.description || 'No description')}</div>
                <div class="item-meta">
                    ${role.personality_traits.map(t => `<span class="badge">${t}</span>`).join('')}
                </div>
            </div>
        `).join('');
    }

    openRoleModal(role = null) {
        const modal = document.getElementById('role-modal');
        const form = document.getElementById('role-form');
        const title = document.getElementById('role-modal-title');

        if (role) {
            title.textContent = 'Edit Role';
            document.getElementById('role-id').value = role.id;
            document.getElementById('role-name').value = role.name;
            document.getElementById('role-type').value = role.role;
            document.getElementById('role-description').value = role.description || '';
            document.getElementById('role-prompt').value = role.system_prompt;
            document.getElementById('role-stance').value = role.debate_stance;
            document.getElementById('role-traits').value = role.personality_traits.join(', ');
            document.getElementById('role-knowledge').value = role.knowledge_base.join(', ');
            this.currentEditingRole = role;
        } else {
            title.textContent = 'New Role';
            form.reset();
            document.getElementById('role-id').value = this.generateId();
            this.currentEditingRole = null;
        }

        this.openModal(modal);
    }

    async handleRoleSave(e) {
        e.preventDefault();

        const role = {
            id: document.getElementById('role-id').value,
            name: document.getElementById('role-name').value,
            role: document.getElementById('role-type').value,
            description: document.getElementById('role-description').value,
            system_prompt: document.getElementById('role-prompt').value,
            debate_stance: document.getElementById('role-stance').value,
            personality_traits: document.getElementById('role-traits').value
                .split(',').map(t => t.trim()).filter(t => t),
            knowledge_base: document.getElementById('role-knowledge').value
                .split(',').map(k => k.trim()).filter(k => k)
        };

        try {
            const method = this.currentEditingRole ? 'PUT' : 'POST';
            const url = this.currentEditingRole ? `/api/roles/${role.id}` : '/api/roles';

            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(role)
            });

            if (response.ok) {
                await this.loadRoles();
                this.closeModal(document.getElementById('role-modal'));
                this.showSuccess('Role saved successfully');
            } else {
                throw new Error('Failed to save role');
            }
        } catch (error) {
            console.error('Error saving role:', error);
            this.showError('Failed to save role');
        }
    }

    async editRole(roleId) {
        const role = this.roles.find(r => r.id === roleId);
        if (role) {
            this.openRoleModal(role);
        }
    }

    async deleteRole(roleId) {
        if (!confirm('Are you sure you want to delete this role?')) {
            return;
        }

        try {
            const response = await fetch(`/api/roles/${roleId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                await this.loadRoles();
                this.showSuccess('Role deleted successfully');
            } else {
                throw new Error('Failed to delete role');
            }
        } catch (error) {
            console.error('Error deleting role:', error);
            this.showError('Failed to delete role');
        }
    }

    // ========================================================================
    // Scenarios Management
    // ========================================================================

    async loadScenarios() {
        try {
            const response = await fetch('/api/scenarios');
            this.scenarios = await response.json();
            this.renderScenarios();
            this.updateScenarioSelect();
        } catch (error) {
            console.error('Failed to load scenarios:', error);
            this.showError('Failed to load scenarios');
        }
    }

    renderScenarios() {
        const scenariosList = document.getElementById('scenarios-list');

        if (this.scenarios.length === 0) {
            scenariosList.innerHTML = '<p class="no-messages">No scenarios available. Create your first scenario!</p>';
            return;
        }

        scenariosList.innerHTML = this.scenarios.map(scenario => `
            <div class="item-card">
                <div class="item-header">
                    <div>
                        <div class="item-title">${this.escapeHtml(scenario.name)}</div>
                        <div class="item-meta">
                            <span class="badge">${scenario.conversation_mode}</span>
                            <span class="badge">${scenario.agents.length} agents</span>
                        </div>
                    </div>
                    <div class="item-actions">
                        <button class="btn btn-secondary btn-small" onclick="app.editScenario('${scenario.id}')">Edit</button>
                        <button class="btn btn-danger btn-small" onclick="app.deleteScenario('${scenario.id}')">Delete</button>
                    </div>
                </div>
                <div class="item-description">${this.escapeHtml(scenario.description || 'No description')}</div>
                <div class="item-meta" style="margin-top: 1rem;">
                    <strong>Topic:</strong> ${this.escapeHtml(scenario.topic)}
                </div>
            </div>
        `).join('');
    }

    updateScenarioSelect() {
        const select = document.getElementById('scenario-select');

        if (this.scenarios.length === 0) {
            select.innerHTML = '<option value="">No scenarios available</option>';
            return;
        }

        select.innerHTML = '<option value="">Select a scenario</option>' +
            this.scenarios.map(s => `
                <option value="${s.id}">${this.escapeHtml(s.name)}</option>
            `).join('');
    }

    openScenarioModal(scenario = null) {
        const modal = document.getElementById('scenario-modal');
        const form = document.getElementById('scenario-form');
        const title = document.getElementById('scenario-modal-title');

        if (scenario) {
            title.textContent = 'Edit Scenario';
            document.getElementById('scenario-id').value = scenario.id;
            document.getElementById('scenario-name').value = scenario.name;
            document.getElementById('scenario-description').value = scenario.description || '';
            document.getElementById('scenario-topic').value = scenario.topic;
            document.getElementById('scenario-mode').value = scenario.conversation_mode;
            document.getElementById('scenario-max-replies').value = scenario.max_replies_before_summary;
            document.getElementById('scenario-timeout').value = scenario.timeout_seconds;
            this.currentEditingScenario = scenario;
            this.renderScenarioAgents(scenario.agents);
        } else {
            title.textContent = 'New Scenario';
            form.reset();
            document.getElementById('scenario-id').value = this.generateId();
            this.currentEditingScenario = null;
            this.renderScenarioAgents([]);
        }

        this.openModal(modal);
    }

    renderScenarioAgents(agents = []) {
        const container = document.getElementById('scenario-agents-list');

        if (agents.length === 0) {
            container.innerHTML = '<p class="item-meta">No agents added yet</p>';
            return;
        }

        container.innerHTML = agents.map((agent, index) => `
            <div class="agent-item">
                <div class="agent-info">
                    <div class="agent-name">${this.escapeHtml(agent.name)}</div>
                    <div class="agent-role">${agent.role}${agent.is_supervisor ? ' (Supervisor)' : ''}</div>
                </div>
                <button type="button" class="btn btn-danger btn-small" onclick="app.removeAgent(${index})">Remove</button>
            </div>
        `).join('');
    }

    addAgentToScenario() {
        const agents = this.getScenarioAgentsFromForm();

        // Show simple prompt for now (could be enhanced with a modal)
        const agentName = prompt('Agent name:');
        if (!agentName) return;

        const roleSelect = document.createElement('select');
        const roles = ['technical', 'creative', 'critical', 'practical', 'visionary', 'analytical', 'supervisor'];

        const agentRole = prompt('Agent role (technical/creative/critical/practical/visionary/analytical/supervisor):');
        if (!agentRole || !roles.includes(agentRole.toLowerCase())) {
            alert('Invalid role');
            return;
        }

        const systemPrompt = prompt('System prompt:');
        if (!systemPrompt) return;

        agents.push({
            name: agentName,
            role: agentRole.toLowerCase(),
            system_prompt: systemPrompt,
            personality_traits: [],
            knowledge_base: [],
            debate_stance: 'balanced',
            is_supervisor: agentRole.toLowerCase() === 'supervisor'
        });

        this.renderScenarioAgents(agents);
    }

    removeAgent(index) {
        const agents = this.getScenarioAgentsFromForm();
        agents.splice(index, 1);
        this.renderScenarioAgents(agents);
    }

    getScenarioAgentsFromForm() {
        if (this.currentEditingScenario) {
            return [...this.currentEditingScenario.agents];
        }
        // Parse from DOM if needed
        return [];
    }

    async handleScenarioSave(e) {
        e.preventDefault();

        const agents = this.getScenarioAgentsFromForm();

        if (agents.length === 0) {
            alert('Please add at least one agent to the scenario');
            return;
        }

        const scenario = {
            id: document.getElementById('scenario-id').value,
            name: document.getElementById('scenario-name').value,
            description: document.getElementById('scenario-description').value,
            topic: document.getElementById('scenario-topic').value,
            conversation_mode: document.getElementById('scenario-mode').value,
            max_replies_before_summary: parseInt(document.getElementById('scenario-max-replies').value),
            timeout_seconds: parseInt(document.getElementById('scenario-timeout').value),
            agents: agents
        };

        try {
            const method = this.currentEditingScenario ? 'PUT' : 'POST';
            const url = this.currentEditingScenario ? `/api/scenarios/${scenario.id}` : '/api/scenarios';

            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(scenario)
            });

            if (response.ok) {
                await this.loadScenarios();
                this.closeModal(document.getElementById('scenario-modal'));
                this.showSuccess('Scenario saved successfully');
            } else {
                throw new Error('Failed to save scenario');
            }
        } catch (error) {
            console.error('Error saving scenario:', error);
            this.showError('Failed to save scenario');
        }
    }

    async editScenario(scenarioId) {
        const scenario = this.scenarios.find(s => s.id === scenarioId);
        if (scenario) {
            this.openScenarioModal(scenario);
        }
    }

    async deleteScenario(scenarioId) {
        if (!confirm('Are you sure you want to delete this scenario?')) {
            return;
        }

        try {
            const response = await fetch(`/api/scenarios/${scenarioId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                await this.loadScenarios();
                this.showSuccess('Scenario deleted successfully');
            } else {
                throw new Error('Failed to delete scenario');
            }
        } catch (error) {
            console.error('Error deleting scenario:', error);
            this.showError('Failed to delete scenario');
        }
    }

    // ========================================================================
    // Swarm Control
    // ========================================================================

    setupSwarmControl() {
        // Already handled in setupForms()
    }

    async updateSwarmStatus() {
        try {
            const response = await fetch('/api/swarm/status');
            this.swarmStatus = await response.json();
            this.renderSwarmStatus();
        } catch (error) {
            console.error('Failed to update swarm status:', error);
        }
    }

    renderSwarmStatus() {
        if (!this.swarmStatus) return;

        document.getElementById('status-text').textContent = this.swarmStatus.status;
        document.getElementById('status-text').className = `status-badge ${this.swarmStatus.status}`;
        document.getElementById('status-scenario').textContent = this.swarmStatus.scenario_name || 'None';
        document.getElementById('status-agents').textContent = this.swarmStatus.agents.length;
        document.getElementById('status-messages').textContent = this.swarmStatus.message_count;

        // Update button states
        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');

        if (this.swarmStatus.active) {
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else {
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    }

    async handleSwarmStart(e) {
        e.preventDefault();

        const scenarioId = document.getElementById('scenario-select').value;
        if (!scenarioId) {
            alert('Please select a scenario');
            return;
        }

        const relayUrls = document.getElementById('relay-urls').value
            .split(',').map(u => u.trim()).filter(u => u);
        const ollamaUrl = document.getElementById('ollama-url').value;

        try {
            const response = await fetch('/api/swarm/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    scenario_id: scenarioId,
                    relay_urls: relayUrls,
                    ollama_base_url: ollamaUrl
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.showSuccess('Swarm started successfully');
                await this.updateSwarmStatus();
            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start swarm');
            }
        } catch (error) {
            console.error('Error starting swarm:', error);
            this.showError(error.message);
        }
    }

    async handleSwarmStop() {
        try {
            const response = await fetch('/api/swarm/stop', {
                method: 'POST'
            });

            if (response.ok) {
                this.showSuccess('Swarm stopped');
                await this.updateSwarmStatus();
            } else {
                throw new Error('Failed to stop swarm');
            }
        } catch (error) {
            console.error('Error stopping swarm:', error);
            this.showError('Failed to stop swarm');
        }
    }

    // ========================================================================
    // WebSocket for Real-time Updates
    // ========================================================================

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/nostr`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            // Send ping every 30 seconds to keep connection alive
            this.wsPingInterval = setInterval(() => {
                if (this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send('ping');
                }
            }, 30000);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            if (this.wsPingInterval) {
                clearInterval(this.wsPingInterval);
            }
            // Reconnect after 5 seconds
            setTimeout(() => this.connectWebSocket(), 5000);
        };
    }

    handleWebSocketMessage(data) {
        console.log('WebSocket message:', data);

        if (data.type === 'pong') {
            return;
        }

        if (data.type === 'swarm_started') {
            this.showSuccess(`Swarm started: ${data.scenario}`);
            this.updateSwarmStatus();
        } else if (data.type === 'swarm_stopped') {
            this.showSuccess('Swarm stopped');
            this.updateSwarmStatus();
        } else if (data.type === 'swarm_completed') {
            this.showSuccess('Swarm completed');
            this.updateSwarmStatus();
        } else if (data.type === 'swarm_error') {
            this.showError(`Swarm error: ${data.error}`);
            this.updateSwarmStatus();
        } else if (data.type === 'message') {
            this.addMessageToConversation(data);
        }
    }

    addMessageToConversation(message) {
        const container = document.getElementById('conversation-messages');
        const noMessages = container.querySelector('.no-messages');
        if (noMessages) {
            noMessages.remove();
        }

        const messageEl = document.createElement('div');
        messageEl.className = 'message';
        messageEl.innerHTML = `
            <div class="message-header">
                <span class="message-author">${this.escapeHtml(message.author || 'Unknown')}</span>
                <span class="message-time">${new Date(message.timestamp * 1000).toLocaleTimeString()}</span>
            </div>
            <div class="message-content">${this.escapeHtml(message.content)}</div>
        `;

        container.appendChild(messageEl);
        container.scrollTop = container.scrollHeight;
    }

    // ========================================================================
    // Utilities
    // ========================================================================

    generateId() {
        return 'id_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showSuccess(message) {
        // Simple alert for now - could be enhanced with toast notifications
        console.log('Success:', message);
    }

    showError(message) {
        // Simple alert for now - could be enhanced with toast notifications
        console.error('Error:', message);
        alert(message);
    }
}

// Initialize the app
const app = new SwarmApp();

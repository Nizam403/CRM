// ==========================================================================
// AuraCRM - Frontend Application Logic
// ==========================================================================

// --- App State ---
const state = {
    currentTab: 'dashboard',
    theme: 'dark',
    stats: {},
    customers: [],
    selectedCustomerId: null,
    leads: [],
    marketingSpends: {},
    campaigns: [],
    selectedLeadIdForStatus: null,
    simulator: {
        budgets: {},    // dept_name -> budget
        historical: {}, // dept_name -> { cpl, roas, leadK, revenueK, spent }
        optimization: null
    }
};

// --- Chart Palette ---
// Cycled by index so any number of departments gets a defined colour.
const CHANNEL_PALETTE = [
    '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#06b6d4',
    '#f43f5e', '#84cc16', '#a855f7', '#14b8a6'
];

// --- Chart Instances ---
let revenueSpendChart = null;
let funnelChart = null;
let spendDeptChart = null;
let roiDeptChart = null;

// --- API Helper Functions ---
const api = {
    async getStats() {
        const res = await fetch('/api/dashboard/stats');
        return res.json();
    },
    async getCustomers(search = '') {
        const url = search ? `/api/customers?search=${encodeURIComponent(search)}` : '/api/customers';
        const res = await fetch(url);
        return res.json();
    },
    async getCustomerDetails(id) {
        const res = await fetch(`/api/customers/${id}`);
        return res.json();
    },
    async getLeads() {
        const res = await fetch('/api/leads');
        return res.json();
    },
    async createLead(leadData) {
        const res = await fetch('/api/leads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(leadData)
        });
        return res.json();
    },
    async updateLeadStatus(id, status) {
        const res = await fetch(`/api/leads/${id}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });
        return res.json();
    },
    async deleteLead(id) {
        const res = await fetch(`/api/leads/${id}`, { method: 'DELETE' });
        return res.json();
    },
    async getMarketingSpends() {
        const res = await fetch('/api/marketing/spends');
        return res.json();
    },
    async getCampaignPerformance() {
        const res = await fetch('/api/marketing/campaigns');
        return res.json();
    },
    async getOptimalAllocation(budget) {
        const url = `/api/marketing/optimize?budget=${encodeURIComponent(budget)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Optimizer failed: ${res.status}`);
        return res.json();
    }
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // Set current date
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('current-date').textContent = new Date().toLocaleDateString('en-US', options);

    // Setup Event Listeners
    setupEventListeners();

    // Load Initial Data
    await loadAllData();

    // Render Dashboard
    renderDashboard();

    // Initialize Simulator
    initSimulator();
});

// --- Event Listeners Setup ---
function setupEventListeners() {
    // Tab Navigation
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const tab = link.getAttribute('data-tab');
            switchTab(tab);
        });
    });

    // Theme Toggle
    const themeToggle = document.getElementById('theme-toggle');
    themeToggle.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        state.theme = newTheme;

        // Update toggle label
        document.querySelector('.theme-label').textContent = newTheme === 'dark' ? 'Dark Mode' : 'Light Mode';

        // Re-render charts to update colors for theme
        updateChartThemes();
    });

    // Customer Search
    const searchInput = document.getElementById('customer-search');
    searchInput.addEventListener('input', debounce(async (e) => {
        state.customers = await api.getCustomers(e.target.value);
        renderCustomerList();
    }, 300));

    // Lead Sort
    const leadSort = document.getElementById('lead-sort');
    leadSort.addEventListener('change', () => {
        renderLeadsPipeline();
    });

    // Add Lead Modal Trigger
    const btnQuickLead = document.getElementById('btn-quick-lead');
    const modalAddLead = document.getElementById('modal-add-lead');
    const btnCloseLeadModal = document.getElementById('btn-close-lead-modal');
    const btnCancelLeadModal = document.getElementById('btn-cancel-lead-modal');

    const openLeadModal = () => modalAddLead.classList.add('active');
    const closeLeadModal = () => {
        modalAddLead.classList.remove('active');
        document.getElementById('form-add-lead').reset();
    };

    btnQuickLead.addEventListener('click', openLeadModal);
    btnCloseLeadModal.addEventListener('click', closeLeadModal);
    btnCancelLeadModal.addEventListener('click', closeLeadModal);

    // Add Lead Form Submit
    const formAddLead = document.getElementById('form-add-lead');
    formAddLead.addEventListener('submit', async (e) => {
        e.preventDefault();
        const leadData = {
            name: document.getElementById('lead-name').value,
            email: document.getElementById('lead-email').value,
            company: document.getElementById('lead-company').value,
            phone: document.getElementById('lead-phone').value,
            value: parseFloat(document.getElementById('lead-value').value),
            score: parseInt(document.getElementById('lead-score').value),
            source: document.getElementById('lead-source').value,
            assigned_to: document.getElementById('lead-assigned').value,
            status: 'New'
        };

        try {
            await api.createLead(leadData);
            closeLeadModal();
            await loadAllData();

            // Refresh current view
            if (state.currentTab === 'dashboard') {
                renderDashboard();
            } else if (state.currentTab === 'leads') {
                renderLeadsPipeline();
            }
            showNotification('Success', 'Lead created successfully!', 'success');
        } catch (err) {
            showNotification('Error', 'Failed to create lead.', 'danger');
        }
    });

    // Status Update Modal Close
    const modalUpdateStatus = document.getElementById('modal-update-status');
    const btnCloseStatusModal = document.getElementById('btn-close-status-modal');
    btnCloseStatusModal.addEventListener('click', () => {
        modalUpdateStatus.classList.remove('active');
    });

    // Status Update Buttons
    document.querySelectorAll('.btn-status').forEach(btn => {
        btn.addEventListener('click', async () => {
            const newStatus = btn.getAttribute('data-status');
            if (state.selectedLeadIdForStatus && newStatus) {
                try {
                    await api.updateLeadStatus(state.selectedLeadIdForStatus, newStatus);
                    modalUpdateStatus.classList.remove('active');
                    await loadAllData();

                    if (state.currentTab === 'leads') {
                        renderLeadsPipeline();
                    } else if (state.currentTab === 'dashboard') {
                        renderDashboard();
                    }

                    showNotification('Success', `Lead status updated to ${newStatus}`, 'success');
                } catch (err) {
                    showNotification('Error', 'Failed to update lead status.', 'danger');
                }
            }
        });
    });

    // Reset Simulator
    document.getElementById('btn-reset-simulator').addEventListener('click', () => {
        state.simulator.optimization = null;
        document.getElementById('optimizer-panel').hidden = true;
        initSimulator();
    });

    // Budget Optimizer
    document.getElementById('btn-optimize').addEventListener('click', runOptimizer);
    document.getElementById('btn-apply-optimizer').addEventListener('click', applyOptimization);
}

// --- Load Data ---
async function loadAllData() {
    try {
        const [stats, customers, leads, spends, campaigns] = await Promise.all([
            api.getStats(),
            api.getCustomers(),
            api.getLeads(),
            api.getMarketingSpends(),
            api.getCampaignPerformance()
        ]);

        state.stats = stats;
        state.customers = customers;
        state.leads = leads;
        state.marketingSpends = spends;
        state.campaigns = campaigns.campaigns || [];
    } catch (err) {
        console.error('Error loading data:', err);
        showNotification('Error', 'Failed to load dashboard data.', 'danger');
    }
}

// --- Tab Switching ---
async function switchTab(tabId) {
    state.currentTab = tabId;

    // Update active nav link
    document.querySelectorAll('.nav-link').forEach(link => {
        if (link.getAttribute('data-tab') === tabId) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });

    // Update active content panel
    document.querySelectorAll('.tab-content').forEach(content => {
        if (content.id === `tab-${tabId}`) {
            content.classList.add('active');
        } else {
            content.classList.remove('active');
        }
    });

    // Update Header Title
    const pageTitle = document.getElementById('page-title');
    const pageSubtitle = document.getElementById('page-subtitle');

    if (tabId === 'dashboard') {
        pageTitle.textContent = 'Dashboard Overview';
        pageSubtitle.textContent = 'Real-time marketing performance and customer insights.';
        renderDashboard();
    } else if (tabId === 'customer360') {
        pageTitle.textContent = 'Customer 360';
        pageSubtitle.textContent = 'Comprehensive profiles, interaction history, and LTV analysis.';
        renderCustomerList();
        renderCustomerDetail();
    } else if (tabId === 'leads') {
        pageTitle.textContent = 'Leads Pipeline';
        pageSubtitle.textContent = 'Manage sales opportunities and track conversion stages.';
        renderLeadsPipeline();
    } else if (tabId === 'spends') {
        pageTitle.textContent = 'Marketing Spends';
        pageSubtitle.textContent = 'Analyze budget allocation, actual spends, and ROI by department.';
        renderMarketingSpends();
    }
}

// --- Render Dashboard ---
function renderDashboard() {
    // Render Stats
    document.getElementById('stat-revenue').textContent = formatCurrency(state.stats.total_revenue);
    document.getElementById('stat-leads').textContent = state.stats.active_leads;
    document.getElementById('stat-spend').textContent = formatCurrency(state.stats.total_spend);
    document.getElementById('stat-conversion').textContent = formatPercent(state.stats.conversion_rate);

    // ROAS was computed by the backend but never rendered. One definition,
    // one card: realised revenue per AED of marketing spend.
    const roasEl = document.getElementById('stat-roas');
    roasEl.textContent = formatMultiplier(state.stats.roas);
    roasEl.className = `stat-value ${roasClass(state.stats.roas)}`;

    // Every KPI above is scoped to the same period as the marketing page.
    const period = state.stats.period;
    if (period) {
        document.querySelectorAll('.stat-period').forEach(el => {
            el.textContent = period.label;
        });
    }

    // Render High-Score Leads Table
    const leadsTbody = document.getElementById('dashboard-leads-tbody');
    leadsTbody.innerHTML = '';

    const highLeads = [...state.leads]
        .sort((a, b) => b.score - a.score)
        .slice(0, 5);

    highLeads.forEach(lead => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${esc(lead.name)}</strong></td>
            <td>${esc(lead.company)}</td>
            <td>${esc(lead.phone)}</td>
            <td>${formatCurrency(lead.value)}</td>
            <td><span class="lead-score-badge ${getScoreClass(lead.score)}">${esc(lead.score)}</span></td>
            <td><span class="lead-status-badge status-${statusClass(lead.status)}">${esc(lead.status)}</span></td>
        `;
        leadsTbody.appendChild(tr);
    });

    // Render Top Customers Table
    const custTbody = document.getElementById('dashboard-customers-tbody');
    custTbody.innerHTML = '';

    const topCustomers = [...state.customers]
        .sort((a, b) => b.ltv - a.ltv)
        .slice(0, 5);

    topCustomers.forEach(cust => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <img src="${safeImg(cust.profile_pic)}" alt="" style="width: 28px; height: 28px; border-radius: 50%; object-fit: cover;">
                    <strong>${esc(cust.name)}</strong>
                </div>
            </td>
            <td>${esc(cust.company)}</td>
            <td>${esc(cust.acquisition_channel)}</td>
            <td class="highlight" style="font-weight: 700;">${formatCurrency(cust.ltv)}</td>
        `;
        custTbody.appendChild(tr);
    });

    // Render Dashboard Charts
    renderDashboardCharts();
}

// --- Render Dashboard Charts ---
function renderDashboardCharts() {
    const isDark = state.theme === 'dark';
    const textColor = isDark ? '#a5a1b8' : '#5c596e';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)';

    // 1. Revenue vs Spend Line Chart
    const trendData = state.marketingSpends.monthly_trend || [];
    const labels = trendData.map(d => d.month);
    const spendData = trendData.map(d => d.spend);
    const revenueData = trendData.map(d => d.revenue);

    if (revenueSpendChart) revenueSpendChart.destroy();

    const ctx1 = document.getElementById('revenueSpendChart').getContext('2d');
    revenueSpendChart = new Chart(ctx1, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Revenue Generated (AED)',
                    data: revenueData,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                },
                {
                    label: 'Marketing Spend (AED)',
                    data: spendData,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: textColor, font: { family: 'Inter' } }
                }
            },
            scales: {
                x: {
                    grid: { color: gridColor },
                    ticks: { color: textColor }
                },
                y: {
                    grid: { color: gridColor },
                    ticks: { color: textColor }
                }
            }
        }
    });

    // 2. Funnel Chart (Horizontal Bar Chart representing pipeline stages)
    const stages = ['New', 'Contacted', 'Qualified', 'Proposal', 'Won'];
    const stageCounts = stages.map(stage => {
        return state.leads.filter(l => l.status === stage).length;
    });

    if (funnelChart) funnelChart.destroy();

    const ctx2 = document.getElementById('funnelChart').getContext('2d');
    funnelChart = new Chart(ctx2, {
        type: 'bar',
        data: {
            labels: stages,
            datasets: [{
                label: 'Leads in Stage',
                data: stageCounts,
                backgroundColor: [
                    'rgba(59, 130, 246, 0.75)',
                    'rgba(245, 158, 11, 0.75)',
                    'rgba(139, 92, 246, 0.75)',
                    'rgba(236, 72, 153, 0.75)',
                    'rgba(16, 185, 129, 0.75)'
                ],
                borderColor: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)',
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: gridColor },
                    ticks: { color: textColor, stepSize: 1 }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: textColor }
                }
            }
        }
    });
}

// --- Render Customer 360 Tab ---
function renderCustomerList() {
    const listContainer = document.getElementById('customer-list-container');
    listContainer.innerHTML = '';

    if (state.customers.length === 0) {
        listContainer.innerHTML = '<div class="empty-state">No customers found</div>';
        return;
    }

    state.customers.forEach(cust => {
        const card = document.createElement('div');
        card.className = `customer-item-card ${state.selectedCustomerId === cust.id ? 'active' : ''}`;
        card.innerHTML = `
            <img src="${safeImg(cust.profile_pic)}" alt="${esc(cust.name)}" class="customer-item-avatar">
            <div class="customer-item-info">
                <span class="customer-item-name">${esc(cust.name)}</span>
                <span class="customer-item-company">${esc(cust.company)}</span>
            </div>
            <span class="customer-item-ltv">${formatCurrency(cust.ltv)}</span>
        `;
        card.addEventListener('click', () => {
            state.selectedCustomerId = cust.id;
            renderCustomerList(); // Refresh active state
            renderCustomerDetail();
        });
        listContainer.appendChild(card);
    });
}

async function renderCustomerDetail() {
    const detailContainer = document.getElementById('customer-detail-container');

    if (!state.selectedCustomerId) {
        detailContainer.innerHTML = `
            <div class="empty-detail-state">
                <i data-lucide="user" class="large-icon"></i>
                <h3>Select a customer to view Customer 360 Profile</h3>
                <p>Get a comprehensive view of interactions, purchases, campaigns, and metrics.</p>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    try {
        const cust = await api.getCustomerDetails(state.selectedCustomerId);

        // Build Customer 360 View
        detailContainer.innerHTML = `
            <div class="customer-detail-header">
                <div class="customer-profile-card">
                    <img src="${safeImg(cust.profile_pic)}" alt="${esc(cust.name)}" class="customer-profile-avatar">
                    <div class="customer-profile-meta">
                        <h2>${esc(cust.name)}</h2>
                        <p>${esc(cust.job_title)} at <strong>${esc(cust.company)}</strong></p>
                        <p style="margin-top: 0.25rem; font-size: 0.8rem; color: var(--text-muted);">
                            <i data-lucide="mail" style="width: 12px; height: 12px; display: inline; vertical-align: middle;"></i> ${esc(cust.email)} |
                            <i data-lucide="phone" style="width: 12px; height: 12px; display: inline; vertical-align: middle;"></i> ${esc(cust.phone)}
                        </p>
                    </div>
                </div>
                <div class="customer-metrics-row">
                    <div class="metric-box">
                        <span class="metric-box-label">Customer Status</span>
                        <span class="badge ${cust.status === 'Active' ? 'status-active' : 'status-inactive'}" style="align-self: flex-end; margin-top: 0.25rem;">${esc(cust.status)}</span>
                    </div>
                    <div class="metric-box">
                        <span class="metric-box-label">Lifetime Value (LTV)</span>
                        <span class="metric-box-value highlight">${formatCurrency(cust.ltv)}</span>
                    </div>
                    <div class="metric-box">
                        <span class="metric-box-label">Acquired Via</span>
                        <span class="metric-box-value" style="font-size: 1rem; color: var(--secondary);">${esc(cust.acquisition_channel)}</span>
                    </div>
                </div>
            </div>

            <div class="customer-360-grid">
                <!-- Interaction Timeline -->
                <div class="detail-section-card">
                    <h4>Interaction Timeline</h4>
                    <div class="timeline">
                        ${cust.interactions.map(item => `
                            <div class="timeline-item ${typeClass(item.type)}">
                                <div class="timeline-dot"></div>
                                <div class="timeline-content">
                                    <div class="timeline-header">
                                        <span class="timeline-title">${esc(item.type)} - ${esc(item.subject)}</span>
                                        <span class="timeline-date">${esc(item.date)}</span>
                                    </div>
                                    <span class="timeline-desc">Status: <strong>${esc(item.status)}</strong> ${item.amount ? `| Amount: ${formatCurrency(item.amount)}` : ''}</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>

                <!-- Purchases & Campaigns -->
                <div style="display: flex; flex-direction: column; gap: 1.5rem;">
                    <!-- Purchases -->
                    <div class="detail-section-card">
                        <h4>Purchase History</h4>
                        <div class="table-responsive">
                            <table class="data-table" style="font-size: 0.8rem;">
                                <thead>
                                    <tr>
                                        <th>Order ID</th>
                                        <th>Date</th>
                                        <th>Item</th>
                                        <th>Amount</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${cust.purchases.length === 0 ? '<tr><td colspan="4" style="text-align: center;">No purchases yet</td></tr>' :
                cust.purchases.map(p => `
                                        <tr>
                                            <td><strong>${esc(p.id)}</strong></td>
                                            <td>${esc(p.date)}</td>
                                            <td>${esc(p.item)}</td>
                                            <td style="font-weight: 700; color: var(--success);">${formatCurrency(p.amount)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Campaigns -->
                    <div class="detail-section-card">
                        <h4>Marketing Campaigns Targeted</h4>
                        <div class="campaign-list">
                            ${cust.campaigns.map(c => `
                                <div class="campaign-item">
                                    <span class="campaign-name">${esc(c.name)}</span>
                                    <span class="lead-status-badge status-${statusClass(c.status)}">${esc(c.status)}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
        lucide.createIcons();
    } catch (err) {
        detailContainer.innerHTML = '<div class="empty-detail-state">Failed to load customer details.</div>';
    }
}

// --- Render Leads Pipeline Tab ---
function renderLeadsPipeline() {
    const sortVal = document.getElementById('lead-sort').value;

    // Sort leads
    let sortedLeads = [...state.leads];
    if (sortVal === 'score') {
        sortedLeads.sort((a, b) => b.score - a.score);
    } else if (sortVal === 'value') {
        sortedLeads.sort((a, b) => b.value - a.value);
    } else if (sortVal === 'date') {
        sortedLeads.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    }

    // Group leads by status
    const columns = {
        'New': [],
        'Contacted': [],
        'Qualified': [],
        'Proposal': [],
        'Won': [],
        'Lost': []
    };

    sortedLeads.forEach(lead => {
        if (columns[lead.status]) {
            columns[lead.status].push(lead);
        }
    });

    // Render columns
    Object.keys(columns).forEach(status => {
        const container = document.getElementById(`cards-${status.toLowerCase()}`);
        const countBadge = document.getElementById(`count-${status.toLowerCase()}`);

        container.innerHTML = '';
        countBadge.textContent = columns[status].length;

        columns[status].forEach(lead => {
            const card = document.createElement('div');
            card.className = 'kanban-card';
            card.draggable = true;
            card.innerHTML = `
                <div class="kanban-card-header">
                    <span class="lead-company">${esc(lead.company)}</span>
                    <span class="lead-score-badge ${getScoreClass(lead.score)}">Score: ${esc(lead.score)}</span>
                </div>
                <div class="lead-name">${esc(lead.name)}</div>
                <div class="lead-phone">
                    <i data-lucide="phone" style="width: 12px; height: 12px;"></i> ${esc(lead.phone || 'No phone')}
                </div>
                <div class="lead-value">${formatCurrency(lead.value)}</div>
                <div class="kanban-card-footer">
                    <span class="lead-source-tag">
                        <i data-lucide="compass"></i> ${esc(lead.source)}
                    </span>
                    <span class="lead-assignee">${esc(lead.assigned_to)}</span>
                </div>
            `;

            // Drag and Drop Events
            card.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('text/plain', lead.id);
                card.style.opacity = '0.5';
            });

            card.addEventListener('dragend', () => {
                card.style.opacity = '1';
            });

            // Double click to open status update modal (alternative to drag & drop for accessibility/mobile)
            card.addEventListener('dblclick', () => {
                openStatusModal(lead.id, lead.name);
            });

            container.appendChild(card);
        });

        // Column Drag Over / Drop
        const colElement = container.parentElement;
        colElement.addEventListener('dragover', (e) => {
            e.preventDefault();
            colElement.style.background = 'rgba(255, 255, 255, 0.05)';
        });

        colElement.addEventListener('dragleave', () => {
            colElement.style.background = '';
        });

        colElement.addEventListener('drop', async (e) => {
            e.preventDefault();
            colElement.style.background = '';
            const leadId = e.dataTransfer.getData('text/plain');
            const targetStatus = colElement.getAttribute('data-status');

            if (leadId && targetStatus) {
                try {
                    await api.updateLeadStatus(leadId, targetStatus);
                    await loadAllData();
                    renderLeadsPipeline();
                    showNotification('Success', `Lead status updated to ${targetStatus}`, 'success');
                } catch (err) {
                    showNotification('Error', 'Failed to update lead status.', 'danger');
                }
            }
        });
    });

    lucide.createIcons();
}

function openStatusModal(leadId, leadName) {
    state.selectedLeadIdForStatus = leadId;
    document.getElementById('status-modal-lead-name').textContent = leadName;
    document.getElementById('modal-update-status').classList.add('active');
}

// --- Render Marketing Spends Tab ---
function renderMarketingSpends() {
    const spends = state.marketingSpends.departments || [];
    const totals = state.marketingSpends.totals || {};
    const period = state.marketingSpends.period;

    // Label the period the figures cover, so revenue and spend are never read
    // as covering different windows.
    const periodEl = document.getElementById('spends-period-label');
    if (periodEl && period) periodEl.textContent = period.label;

    const tbody = document.getElementById('spends-table-tbody');
    tbody.innerHTML = '';

    if (spends.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" style="text-align: center;">No marketing departments configured</td></tr>';
        renderCampaignPerformance();
        renderSpendsCharts();
        return;
    }

    // Worst-performing channel by ROAS, flagged inline. This is the insight the
    // page exists to surface and it was previously invisible.
    const ranked = spends.filter(d => d.roas !== null && d.roas !== undefined)
        .sort((a, b) => a.roas - b.roas);
    const worst = ranked.length ? ranked[0].name : null;

    spends.forEach(dept => {
        const tr = document.createElement('tr');
        const flag = dept.name === worst
            ? ' <span class="dept-flag" title="Lowest return on ad spend">worst ROAS</span>'
            : '';
        tr.innerHTML = `
            <td><strong>${esc(dept.name)}</strong>${flag}</td>
            <td>${formatCurrency(dept.budget)}</td>
            <td>${formatCurrency(dept.spent)}</td>
            <td class="${utilizationClass(dept.utilization)}">${formatPercent(dept.utilization)}</td>
            <td class="${paceClass(dept.pace_index)}" title="${paceTitle(dept.pace_index)}">${formatMultiplier(dept.pace_index)}</td>
            <td>${esc(dept.leads_generated)}</td>
            <td>${esc(dept.customers_acquired)}</td>
            <td>${formatCurrency(dept.cpl)}</td>
            <td>${formatCurrency(dept.cac)}</td>
            <td>${formatPercent(dept.win_rate)}</td>
            <td>${formatCurrency(dept.revenue)}</td>
            <td class="${roasClass(dept.roas)}">${formatMultiplier(dept.roas)}</td>
        `;
        tbody.appendChild(tr);
    });

    // Totals row, so the channel rows visibly reconcile with the company figure.
    const tfoot = document.getElementById('spends-table-tfoot');
    if (tfoot) {
        tfoot.innerHTML = `
            <tr class="totals-row">
                <td><strong>All channels</strong></td>
                <td>${formatCurrency(totals.budget)}</td>
                <td>${formatCurrency(totals.spent)}</td>
                <td class="${utilizationClass(totals.utilization)}">${formatPercent(totals.utilization)}</td>
                <td class="${paceClass(totals.pace_index)}">${formatMultiplier(totals.pace_index)}</td>
                <td>${esc(totals.leads_generated)}</td>
                <td>${esc(totals.customers_acquired)}</td>
                <td>${formatCurrency(totals.cpl)}</td>
                <td>${formatCurrency(totals.cac)}</td>
                <td>—</td>
                <td>${formatCurrency(totals.attributed_revenue)}</td>
                <td class="${roasClass(totals.attributed_roas)}">${formatMultiplier(totals.attributed_roas)}</td>
            </tr>
        `;
    }

    // Revenue that landed in the window but traces to no paid channel.
    const unattrEl = document.getElementById('spends-unattributed');
    if (unattrEl) {
        const unattributed = totals.unattributed_revenue || 0;
        unattrEl.textContent = unattributed > 0
            ? `${formatCurrency(unattributed)} of revenue came from referral/direct and is excluded from channel ROAS. Blended ROAS: ${formatMultiplier(totals.blended_roas)}.`
            : '';
    }

    renderCampaignPerformance();
    renderSpendsCharts();
}

// --- Render Campaign Performance (drilldown beneath channels) ---
function renderCampaignPerformance() {
    const tbody = document.getElementById('campaigns-table-tbody');
    if (!tbody) return;

    const campaigns = state.campaigns || [];
    tbody.innerHTML = '';

    if (campaigns.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align: center;">No campaigns recorded</td></tr>';
        return;
    }

    campaigns.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${esc(c.name)}</strong></td>
            <td>${esc(c.department)}</td>
            <td>${formatCurrency(c.budget)}</td>
            <td>${esc(c.customers_reached)}</td>
            <td>${renderEngagementBar(c.engagement, c.customers_reached)}</td>
            <td>${esc(c.conversions)}</td>
            <td>${formatPercent(c.conversion_rate)}</td>
            <td>${formatCurrency(c.cost_per_conversion)}</td>
            <td>${formatCurrency(c.revenue)}</td>
            <td class="${roasClass(c.roas)}">${formatMultiplier(c.roas)}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Compact stacked bar of the engagement funnel, weakest segment first.
const ENGAGEMENT_ORDER = ['Ignored', 'Opened', 'Clicked', 'Registered', 'Converted'];
const ENGAGEMENT_COLORS = {
    Ignored: 'var(--text-muted)',
    Opened: '#3b82f6',
    Clicked: '#8b5cf6',
    Registered: '#f59e0b',
    Converted: '#10b981'
};

function renderEngagementBar(engagement, reached) {
    if (!engagement || !reached) return '<span class="muted">—</span>';
    const segments = ENGAGEMENT_ORDER
        .filter(stage => engagement[stage] > 0)
        .map(stage => {
            const pct = (engagement[stage] / reached) * 100;
            return `<span class="engagement-seg"
                          style="width:${pct.toFixed(1)}%; background:${ENGAGEMENT_COLORS[stage]}"
                          title="${esc(stage)}: ${esc(engagement[stage])}"></span>`;
        })
        .join('');
    return `<span class="engagement-bar">${segments}</span>`;
}

function renderSpendsCharts() {
    const depts = state.marketingSpends.departments || [];
    const labels = depts.map(d => d.name);
    const spentData = depts.map(d => d.spent);
    // Channels with undefined ROAS plot as 0 rather than breaking the scale.
    const roasData = depts.map(d => (d.roas === null || d.roas === undefined) ? 0 : d.roas);

    const isDark = state.theme === 'dark';
    const textColor = isDark ? '#a5a1b8' : '#5c596e';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)';

    // 1. Spend by Department (Doughnut)
    if (spendDeptChart) spendDeptChart.destroy();
    const ctx1 = document.getElementById('spendDeptChart').getContext('2d');
    spendDeptChart = new Chart(ctx1, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: spentData,
                // Cycled, so a 7th department does not get an undefined colour.
                backgroundColor: labels.map((_, i) => CHANNEL_PALETTE[i % CHANNEL_PALETTE.length]),
                borderWidth: isDark ? 2 : 1,
                borderColor: isDark ? '#15102a' : '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: textColor, font: { family: 'Inter' } }
                }
            }
        }
    });

    // 2. ROI by Department (Bar)
    if (roiDeptChart) roiDeptChart.destroy();
    const ctx2 = document.getElementById('roiDeptChart').getContext('2d');
    roiDeptChart = new Chart(ctx2, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'ROAS (revenue per AED spent)',
                data: roasData,
                // Red below break-even, amber up to 3x, green above. Painting
                // every bar green hid the fact that channels were losing money.
                backgroundColor: roasData.map(v =>
                    v >= 3 ? 'rgba(16, 185, 129, 0.75)'
                        : v >= 1 ? 'rgba(245, 158, 11, 0.75)'
                            : 'rgba(239, 68, 68, 0.75)'),
                borderColor: roasData.map(v =>
                    v >= 3 ? '#10b981' : v >= 1 ? '#f59e0b' : '#ef4444'),
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.parsed.y.toFixed(2)}x return`
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: textColor }
                },
                y: {
                    grid: { color: gridColor },
                    ticks: { color: textColor }
                }
            }
        }
    });
}

// --- Budget Optimization Simulator ---
function initSimulator() {
    const depts = state.marketingSpends.departments || [];
    const container = document.getElementById('simulator-sliders-container');
    container.innerHTML = '';

    state.simulator.budgets = {};
    state.simulator.historical = {};

    depts.forEach(dept => {
        state.simulator.budgets[dept.name] = dept.spent;
        // Response-curve coefficients come from the backend, fitted per channel
        // so y = k*sqrt(x) passes through its observed spend/leads/revenue.
        const response = dept.response || {};
        state.simulator.historical[dept.name] = {
            cpl: dept.cpl,
            roas: dept.roas,
            spent: dept.spent,
            leadK: response.lead_k,
            revenueK: response.revenue_k
        };

        const sliderGroup = document.createElement('div');
        sliderGroup.className = 'slider-group';
        // Keep the slider usable even when a department has no budget set.
        const sliderMax = Math.max(dept.budget * 2, dept.spent * 2, 10000);
        sliderGroup.innerHTML = `
            <div class="slider-header">
                <span class="slider-name">${esc(dept.name)}</span>
                <span class="slider-val" id="val-${slugify(dept.name)}">${formatCurrency(dept.spent)}</span>
            </div>
            <input type="range"
                   class="range-input"
                   id="slide-${slugify(dept.name)}"
                   min="0"
                   max="${sliderMax}"
                   value="${dept.spent}"
                   step="1000">
        `;

        const slider = sliderGroup.querySelector('input');
        slider.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            state.simulator.budgets[dept.name] = val;
            document.getElementById(`val-${slugify(dept.name)}`).textContent = formatCurrency(val);
            calculateSimulation();
        });

        container.appendChild(sliderGroup);
    });

    calculateSimulation();
}

// Projected output for one channel under the diminishing-returns curve.
// Mirrors analytics.project_channel on the backend.
function projectChannel(coefficient, budget) {
    if (!coefficient || budget <= 0) return 0;
    return coefficient * Math.sqrt(budget);
}

function calculateSimulation() {
    let totalBudget = 0;
    let projectedLeads = 0;
    let projectedRevenue = 0;
    let baselineRevenue = 0;
    const unmodelled = [];

    Object.keys(state.simulator.budgets).forEach(name => {
        const budget = state.simulator.budgets[name];
        const hist = state.simulator.historical[name];

        totalBudget += budget;
        projectedLeads += projectChannel(hist.leadK, budget);
        projectedRevenue += projectChannel(hist.revenueK, budget);
        baselineRevenue += projectChannel(hist.revenueK, hist.spent);

        // A channel with no historical leads or revenue has no curve to fit.
        // Name it rather than quietly forecasting zero.
        if (!hist.leadK || !hist.revenueK) unmodelled.push(name);
    });

    document.getElementById('sim-total-budget').textContent = formatCurrency(totalBudget);
    document.getElementById('sim-projected-leads').textContent = Math.round(projectedLeads);
    document.getElementById('sim-projected-revenue').textContent = formatCurrency(projectedRevenue);

    const noteEl = document.getElementById('sim-note');
    if (noteEl) {
        const notes = [];
        if (baselineRevenue > 0) {
            const delta = projectedRevenue - baselineRevenue;
            const pct = (delta / baselineRevenue) * 100;
            notes.push(`${delta >= 0 ? '+' : ''}${formatCurrency(delta)} (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%) vs. current spend.`);
        }
        if (unmodelled.length) {
            notes.push(`No historical baseline for ${unmodelled.join(', ')} — excluded from this projection.`);
        }
        noteEl.textContent = notes.join(' ');
    }
}

// --- Budget Optimizer ---
async function runOptimizer() {
    const panel = document.getElementById('optimizer-panel');
    const btn = document.getElementById('btn-optimize');
    const totalBudget = Object.values(state.simulator.budgets).reduce((a, b) => a + b, 0);

    btn.disabled = true;
    try {
        const result = await api.getOptimalAllocation(totalBudget);
        state.simulator.optimization = result;
        renderOptimizer(result);
        panel.hidden = false;
    } catch (err) {
        showNotification('Error', 'Could not compute an allocation.', 'danger');
    } finally {
        btn.disabled = false;
        lucide.createIcons();
    }
}

function renderOptimizer(result) {
    const summary = document.getElementById('optimizer-summary');
    const tbody = document.getElementById('optimizer-tbody');
    const note = document.getElementById('optimizer-note');
    const applyBtn = document.getElementById('btn-apply-optimizer');

    if (!result.feasible) {
        summary.innerHTML = `<p class="muted">${esc(result.reason)}</p>`;
        tbody.innerHTML = '';
        note.textContent = '';
        applyBtn.hidden = true;
        return;
    }

    applyBtn.hidden = false;
    const uplift = result.revenue_uplift;
    summary.innerHTML = `
        <div class="optimizer-headline">
            <span class="optimizer-headline-label">Reallocating ${formatCurrency(result.total_budget)} could yield</span>
            <span class="optimizer-headline-value ${uplift >= 0 ? 'roas-strong' : 'roas-poor'}">
                ${uplift >= 0 ? '+' : ''}${formatCurrency(uplift)}
            </span>
            <span class="optimizer-headline-label">
                (${formatPercent(result.revenue_uplift_pct)} vs. the current split)
            </span>
        </div>
    `;

    tbody.innerHTML = '';
    result.allocations.forEach(row => {
        const tr = document.createElement('tr');
        const dir = row.delta > 0 ? 'delta-up' : row.delta < 0 ? 'delta-down' : '';
        const capFlag = row.capped
            ? ' <span class="dept-flag cap-flag" title="Held at the maximum increase this channel could absorb">capped</span>'
            : '';
        tr.innerHTML = `
            <td><strong>${esc(row.name)}</strong>${capFlag}</td>
            <td>${formatCurrency(row.current)}</td>
            <td><strong>${formatCurrency(row.recommended)}</strong></td>
            <td class="${dir}">${row.delta >= 0 ? '+' : ''}${formatCurrency(row.delta)}</td>
            <td>${formatCurrency(row.projected_revenue)}</td>
        `;
        tbody.appendChild(tr);
    });

    const notes = [`No channel is given more than ${result.max_spend_multiple}x its current spend — an uncapped optimum recommends increases no channel could absorb.`];
    if (result.unallocated > 0) {
        notes.push(`${formatCurrency(result.unallocated)} could not be deployed productively within those caps.`);
    }
    note.textContent = notes.join(' ');
}

// Push the recommendation into the sliders so it can be adjusted by hand.
function applyOptimization() {
    const result = state.simulator.optimization;
    if (!result || !result.feasible) return;

    result.allocations.forEach(row => {
        if (!(row.name in state.simulator.budgets)) return;
        state.simulator.budgets[row.name] = row.recommended;
        const slider = document.getElementById(`slide-${slugify(row.name)}`);
        const label = document.getElementById(`val-${slugify(row.name)}`);
        if (slider) {
            // The recommendation can exceed the slider's original ceiling.
            if (row.recommended > Number(slider.max)) slider.max = Math.ceil(row.recommended);
            slider.value = row.recommended;
        }
        if (label) label.textContent = formatCurrency(row.recommended);
    });

    calculateSimulation();
    showNotification('Applied', 'Recommended allocation loaded into the sliders.', 'success');
}

// --- Theme Update Helper ---
function updateChartThemes() {
    if (state.currentTab === 'dashboard') {
        renderDashboardCharts();
    } else if (state.currentTab === 'spends') {
        renderSpendsCharts();
    }
}

// --- Utility Functions ---

// Escape text before it goes into innerHTML. Lead names, companies and sources
// are user-supplied via the New Lead modal and are rendered on the dashboard,
// the kanban board and the customer profile -- without this they are a stored
// XSS vector. Quotes are escaped too, so this is also safe inside an attribute.
const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
function esc(val) {
    if (val === null || val === undefined) return '';
    return String(val).replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);
}

// Only allow http(s) image URLs, so a stored `javascript:` or `data:` value
// cannot be smuggled into a src attribute.
function safeImg(url) {
    const raw = String(url || '').trim();
    return /^https?:\/\//i.test(raw) ? esc(raw) : '';
}

// Turn a value into a CSS-safe modifier suffix (used for status- classes).
function statusClass(val) {
    return String(val || '').toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

// Sanitise a value used as a bare class list, preserving the existing
// whitespace-splitting behaviour that style.css relies on: "Support Ticket"
// must stay two classes so `.timeline-item.Support` keeps matching.
function typeClass(val) {
    return String(val || '')
        .split(/\s+/)
        .map(token => token.replace(/[^A-Za-z0-9_-]/g, ''))
        .filter(Boolean)
        .join(' ');
}

function formatCurrency(val) {
    if (val === null || val === undefined || !isFinite(val)) return '—';
    return new Intl.NumberFormat('en-AE', {
        style: 'currency',
        currency: 'AED',
        maximumFractionDigits: 0
    }).format(val);
}

// Ratios and percentages the backend leaves undefined (divide-by-zero) arrive
// as null and render as an em dash rather than "∞" or "NaN".
function formatMultiplier(val) {
    return (val === null || val === undefined || !isFinite(val)) ? '—' : `${val.toFixed(2)}x`;
}

function formatPercent(val) {
    return (val === null || val === undefined || !isFinite(val)) ? '—' : `${val.toFixed(1)}%`;
}

// ROAS below 1.0x is losing money. Colour by threshold instead of painting
// every channel green regardless of value.
function roasClass(roas) {
    if (roas === null || roas === undefined || !isFinite(roas)) return 'roas-unknown';
    if (roas >= 3) return 'roas-strong';
    if (roas >= 1) return 'roas-ok';
    return 'roas-poor';
}

function utilizationClass(pct) {
    if (pct === null || pct === undefined || !isFinite(pct)) return '';
    if (pct > 100) return 'util-over';
    if (pct >= 90) return 'util-high';
    return '';
}

// Pace compares spend rate against time elapsed: 1.00x is exactly on plan.
// 92% of budget spent is alarming in September and fine in December; raw
// utilisation cannot distinguish the two.
function paceClass(pace) {
    if (pace === null || pace === undefined || !isFinite(pace)) return '';
    if (pace >= 1.15) return 'pace-over';
    if (pace <= 0.85) return 'pace-under';
    return 'pace-on';
}

function paceTitle(pace) {
    if (pace === null || pace === undefined || !isFinite(pace)) return 'No budget set';
    if (pace >= 1.15) return `Overspending — burning budget ${((pace - 1) * 100).toFixed(0)}% faster than the year is passing`;
    if (pace <= 0.85) return `Underspending — ${((1 - pace) * 100).toFixed(0)}% behind an even burn`;
    return 'On plan';
}

function getScoreClass(score) {
    if (score >= 80) return 'score-high';
    if (score >= 50) return 'score-medium';
    return 'score-low';
}

function slugify(text) {
    return text.toString().toLowerCase()
        .replace(/\s+/g, '-')           // Replace spaces with -
        .replace(/[^\w\-]+/g, '')       // Remove all non-word chars
        .replace(/\-\-+/g, '-')         // Replace multiple - with single -
        .replace(/^-+/, '')             // Trim - from start
        .replace(/-+$/, '');            // Trim - from end
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Custom Notification System
function showNotification(title, message, type = 'info') {
    // Create notification element
    const notif = document.createElement('div');
    notif.className = `glass-card notification-toast toast-${type}`;
    notif.style.position = 'fixed';
    notif.style.bottom = '20px';
    notif.style.right = '20px';
    notif.style.padding = '1rem 1.5rem';
    notif.style.zIndex = '9999';
    notif.style.display = 'flex';
    notif.style.flexDirection = 'column';
    notif.style.gap = '0.25rem';
    notif.style.borderLeft = `4px solid var(--${type === 'danger' ? 'danger' : type})`;
    notif.style.animation = 'slideIn 0.3s ease forwards';

    notif.innerHTML = `
        <strong style="font-size: 0.9rem; color: var(--text-primary);">${esc(title)}</strong>
        <span style="font-size: 0.8rem; color: var(--text-secondary);">${esc(message)}</span>
    `;

    document.body.appendChild(notif);

    // Remove after 3 seconds
    setTimeout(() => {
        notif.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => notif.remove(), 300);
    }, 3000);
}

// Add CSS keyframes for notification dynamically if not in style.css
const style = document.createElement('style');
style.textContent = `
@keyframes slideIn {
    from { transform: translateX(120%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}
@keyframes slideOut {
    from { transform: translateX(0); opacity: 1; }
    to { transform: translateX(120%); opacity: 0; }
}
.notification-toast {
    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    min-width: 280px;
}
`;
document.head.appendChild(style);

/**
 * SocialHub.AI Skills Store
 * Frontend Application
 */

// Skills Data (Demo Mode)
const SKILLS_DATA = [
    {
        name: "data-export-plus",
        displayName: "高级数据导出",
        description: "支持更多格式的数据导出，包括 Parquet、Feather、JSON Lines 等大数据格式",
        version: "1.2.0",
        author: "SocialHub Official",
        category: "data",
        downloads: 15680,
        rating: 4.8,
        tags: ["export", "parquet", "data-format"],
        certified: true,
        icon: "📦",
        permissions: ["file:write", "data:read"],
        commands: [
            { name: "export-parquet", description: "导出数据为 Parquet 格式" },
            { name: "export-feather", description: "导出数据为 Feather 格式" },
            { name: "export-jsonl", description: "导出数据为 JSON Lines 格式" }
        ],
        readme: "高级数据导出工具支持多种大数据格式，适合与数据仓库和分析平台对接。"
    },
    {
        name: "wechat-analytics",
        displayName: "微信数据分析",
        description: "深度分析微信渠道用户行为、互动数据和转化漏斗，洞察私域流量价值",
        version: "2.1.0",
        author: "SocialHub Official",
        category: "analytics",
        downloads: 28450,
        rating: 4.9,
        tags: ["wechat", "analytics", "funnel"],
        certified: true,
        icon: "💬",
        permissions: ["data:read", "network:internet"],
        commands: [
            { name: "wechat-overview", description: "微信渠道数据概览" },
            { name: "wechat-funnel", description: "分析转化漏斗" },
            { name: "wechat-users", description: "用户行为分析" }
        ],
        readme: "专为微信生态设计的数据分析工具，帮助品牌深入了解私域用户。"
    },
    {
        name: "campaign-optimizer",
        displayName: "营销活动优化器",
        description: "AI 驱动的营销活动优化建议，提升 ROI 和转化率，智能推荐最佳发送时间",
        version: "1.5.0",
        author: "SocialHub Official",
        category: "marketing",
        downloads: 12300,
        rating: 4.7,
        tags: ["campaign", "optimization", "ai"],
        certified: true,
        icon: "🚀",
        permissions: ["data:read", "data:write"],
        commands: [
            { name: "optimize", description: "优化活动配置" },
            { name: "suggest-time", description: "推荐最佳发送时间" },
            { name: "predict-roi", description: "预测活动 ROI" }
        ],
        readme: "使用机器学习算法分析历史活动数据，为您的营销活动提供优化建议。"
    },
    {
        name: "customer-rfm",
        displayName: "RFM 客户分析",
        description: "基于 RFM 模型的客户价值分析和自动分群，识别高价值客户",
        version: "1.0.0",
        author: "SocialHub Official",
        category: "analytics",
        downloads: 9800,
        rating: 4.6,
        tags: ["rfm", "segmentation", "customer-value"],
        certified: true,
        icon: "📊",
        permissions: ["data:read"],
        commands: [
            { name: "rfm-analyze", description: "执行 RFM 分析" },
            { name: "rfm-segment", description: "自动客户分群" },
            { name: "rfm-report", description: "生成分析报告" }
        ],
        readme: "经典的 RFM 分析模型，帮助您识别最有价值的客户群体。"
    },
    {
        name: "sms-batch-sender",
        displayName: "短信批量发送",
        description: "高效的短信批量发送工具，支持模板变量、发送调度和送达报告",
        version: "2.0.0",
        author: "SocialHub Official",
        category: "marketing",
        downloads: 18900,
        rating: 4.5,
        tags: ["sms", "batch", "messaging"],
        certified: true,
        icon: "📱",
        permissions: ["data:read", "network:internet"],
        commands: [
            { name: "sms-send", description: "发送批量短信" },
            { name: "sms-schedule", description: "定时发送任务" },
            { name: "sms-report", description: "查看发送报告" }
        ],
        readme: "企业级短信发送解决方案，支持大批量发送和实时状态追踪。"
    },
    {
        name: "data-sync-tool",
        displayName: "数据同步工具",
        description: "与主流 CRM、ERP 系统的数据双向同步，支持 Salesforce、SAP 等",
        version: "1.3.0",
        author: "SocialHub Official",
        category: "integration",
        downloads: 7500,
        rating: 4.4,
        tags: ["sync", "crm", "integration"],
        certified: true,
        icon: "🔄",
        permissions: ["data:read", "data:write", "network:internet"],
        commands: [
            { name: "sync-pull", description: "从外部系统拉取数据" },
            { name: "sync-push", description: "推送数据到外部系统" },
            { name: "sync-status", description: "查看同步状态" }
        ],
        readme: "一站式数据同步解决方案，打通您的所有业务系统。"
    },
    {
        name: "report-generator",
        displayName: "报表生成器",
        description: "自动化生成多维度业务报表，支持定时发送和多种导出格式",
        version: "1.1.0",
        author: "SocialHub Official",
        category: "utility",
        downloads: 21000,
        rating: 4.8,
        tags: ["report", "automation", "schedule"],
        certified: true,
        icon: "📈",
        permissions: ["data:read", "file:write"],
        commands: [
            { name: "report-create", description: "创建报表模板" },
            { name: "report-generate", description: "生成报表" },
            { name: "report-schedule", description: "设置定时生成" }
        ],
        readme: "告别手动制表，自动生成专业的业务报表。"
    },
    {
        name: "loyalty-calculator",
        displayName: "会员积分计算器",
        description: "灵活的积分规则配置和批量积分计算工具，支持多种积分场景",
        version: "1.0.0",
        author: "SocialHub Official",
        category: "utility",
        downloads: 5600,
        rating: 4.3,
        tags: ["points", "loyalty", "calculator"],
        certified: true,
        icon: "🎯",
        permissions: ["data:read", "data:write"],
        commands: [
            { name: "points-calc", description: "计算积分" },
            { name: "points-batch", description: "批量发放积分" },
            { name: "points-rules", description: "管理积分规则" }
        ],
        readme: "全面的积分管理工具，支持复杂的积分规则配置。"
    }
];

// State
let currentCategory = 'all';
let currentSort = 'downloads';
let searchQuery = '';

// DOM Elements
const skillsGrid = document.getElementById('skillsGrid');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const categoryTabs = document.getElementById('categoryTabs');
const sortSelect = document.getElementById('sortSelect');
const skillModal = document.getElementById('skillModal');
const modalBody = document.getElementById('modalBody');
const modalClose = document.getElementById('modalClose');
const cliBtn = document.getElementById('cliBtn');
const cliModal = document.getElementById('cliModal');
const cliModalClose = document.getElementById('cliModalClose');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    renderSkills();
    setupEventListeners();
});

// Event Listeners
function setupEventListeners() {
    // Search
    searchBtn.addEventListener('click', handleSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });

    // Categories
    categoryTabs.addEventListener('click', (e) => {
        const tab = e.target.closest('.category-tab');
        if (tab) {
            document.querySelectorAll('.category-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentCategory = tab.dataset.category;
            renderSkills();
        }
    });

    // Sort
    sortSelect.addEventListener('change', (e) => {
        currentSort = e.target.value;
        renderSkills();
    });

    // Skill Modal
    modalClose.addEventListener('click', closeSkillModal);
    skillModal.querySelector('.modal-overlay').addEventListener('click', closeSkillModal);

    // CLI Modal
    cliBtn.addEventListener('click', () => cliModal.classList.add('active'));
    cliModalClose.addEventListener('click', () => cliModal.classList.remove('active'));
    cliModal.querySelector('.modal-overlay').addEventListener('click', () => cliModal.classList.remove('active'));

    // Copy buttons
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('copy-btn')) {
            const code = e.target.dataset.code;
            navigator.clipboard.writeText(code).then(() => {
                const originalText = e.target.textContent;
                e.target.textContent = '已复制!';
                setTimeout(() => e.target.textContent = originalText, 1500);
            });
        }
    });

    // Keyboard
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSkillModal();
            cliModal.classList.remove('active');
        }
    });
}

// Search Handler
function handleSearch() {
    searchQuery = searchInput.value.trim().toLowerCase();
    renderSkills();
}

// Filter and Sort Skills
function getFilteredSkills() {
    let skills = [...SKILLS_DATA];

    // Filter by category
    if (currentCategory !== 'all') {
        skills = skills.filter(s => s.category === currentCategory);
    }

    // Filter by search query
    if (searchQuery) {
        skills = skills.filter(s =>
            s.name.toLowerCase().includes(searchQuery) ||
            s.displayName.toLowerCase().includes(searchQuery) ||
            s.description.toLowerCase().includes(searchQuery) ||
            s.tags.some(t => t.toLowerCase().includes(searchQuery))
        );
    }

    // Sort
    switch (currentSort) {
        case 'downloads':
            skills.sort((a, b) => b.downloads - a.downloads);
            break;
        case 'rating':
            skills.sort((a, b) => b.rating - a.rating);
            break;
        case 'newest':
            skills.sort((a, b) => parseFloat(b.version) - parseFloat(a.version));
            break;
    }

    return skills;
}

// Render Skills Grid
function renderSkills() {
    const skills = getFilteredSkills();

    if (skills.length === 0) {
        skillsGrid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="11" cy="11" r="8"></circle>
                    <path d="m21 21-4.35-4.35"></path>
                </svg>
                <h3>未找到技能</h3>
                <p>尝试更换搜索关键词或分类</p>
            </div>
        `;
        return;
    }

    skillsGrid.innerHTML = skills.map(skill => createSkillCard(skill)).join('');

    // Add click listeners to cards
    document.querySelectorAll('.skill-card').forEach(card => {
        card.addEventListener('click', () => {
            const skillName = card.dataset.skill;
            const skill = SKILLS_DATA.find(s => s.name === skillName);
            if (skill) openSkillModal(skill);
        });
    });
}

// Create Skill Card HTML
function createSkillCard(skill) {
    const stars = '★'.repeat(Math.floor(skill.rating)) + '☆'.repeat(5 - Math.floor(skill.rating));

    return `
        <div class="skill-card" data-skill="${skill.name}">
            <div class="skill-header">
                <div class="skill-icon ${skill.category}">${skill.icon}</div>
                <div class="skill-info">
                    <div class="skill-name">
                        ${skill.displayName}
                        ${skill.certified ? '<span class="certified-badge" title="官方认证">✓</span>' : ''}
                    </div>
                    <div class="skill-author">by ${skill.author}</div>
                </div>
            </div>
            <div class="skill-description">${skill.description}</div>
            <div class="skill-tags">
                ${skill.tags.slice(0, 3).map(tag => `<span class="skill-tag">${tag}</span>`).join('')}
            </div>
            <div class="skill-footer">
                <div class="skill-stats">
                    <div class="skill-stat">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        ${formatNumber(skill.downloads)}
                    </div>
                    <div class="skill-stat skill-rating">
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                        </svg>
                        ${skill.rating.toFixed(1)}
                    </div>
                </div>
                <span class="skill-version">v${skill.version}</span>
            </div>
        </div>
    `;
}

// Format Number
function formatNumber(num) {
    if (num >= 10000) {
        return (num / 10000).toFixed(1) + '万';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'k';
    }
    return num.toString();
}

// Open Skill Modal
function openSkillModal(skill) {
    const stars = '★'.repeat(Math.floor(skill.rating)) + '☆'.repeat(5 - Math.floor(skill.rating));

    modalBody.innerHTML = `
        <div class="skill-detail-header">
            <div class="skill-detail-icon skill-icon ${skill.category}">${skill.icon}</div>
            <div class="skill-detail-info">
                <h2>
                    ${skill.displayName}
                    ${skill.certified ? '<span class="certified-badge" title="官方认证">✓</span>' : ''}
                </h2>
                <div class="skill-author">by ${skill.author}</div>
                <div class="skill-detail-meta">
                    <span><strong>${formatNumber(skill.downloads)}</strong> 下载</span>
                    <span class="skill-rating">${stars} ${skill.rating.toFixed(1)}</span>
                    <span>v${skill.version}</span>
                </div>
            </div>
        </div>

        <div class="skill-detail-actions">
            <button class="btn btn-primary btn-lg" onclick="copyInstallCommand('${skill.name}')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                安装技能
            </button>
            <button class="btn btn-secondary btn-lg" onclick="window.open('https://skills.socialhub.ai/${skill.name}', '_blank')">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                    <polyline points="15 3 21 3 21 9"></polyline>
                    <line x1="10" y1="14" x2="21" y2="3"></line>
                </svg>
                查看详情
            </button>
        </div>

        <div class="skill-detail-tabs">
            <button class="skill-detail-tab active" data-tab="overview">概览</button>
            <button class="skill-detail-tab" data-tab="commands">命令</button>
            <button class="skill-detail-tab" data-tab="permissions">权限</button>
        </div>

        <div class="skill-detail-content" id="skillDetailContent">
            <h3>描述</h3>
            <p>${skill.description}</p>
            <p>${skill.readme}</p>

            <h3>标签</h3>
            <div class="skill-tags">
                ${skill.tags.map(tag => `<span class="skill-tag">${tag}</span>`).join('')}
            </div>
        </div>
    `;

    // Tab switching
    const tabs = modalBody.querySelectorAll('.skill-detail-tab');
    const content = modalBody.querySelector('#skillDetailContent');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const tabName = tab.dataset.tab;
            if (tabName === 'overview') {
                content.innerHTML = `
                    <h3>描述</h3>
                    <p>${skill.description}</p>
                    <p>${skill.readme}</p>

                    <h3>标签</h3>
                    <div class="skill-tags">
                        ${skill.tags.map(tag => `<span class="skill-tag">${tag}</span>`).join('')}
                    </div>
                `;
            } else if (tabName === 'commands') {
                content.innerHTML = `
                    <h3>可用命令</h3>
                    <div class="command-list">
                        ${skill.commands.map(cmd => `
                            <div class="command-item">
                                <span class="command-name">${cmd.name}</span>
                                <span class="command-desc">${cmd.description}</span>
                            </div>
                        `).join('')}
                    </div>
                    <h3 style="margin-top: 24px;">CLI 使用示例</h3>
                    <div class="code-block" style="margin-top: 12px;">
                        <code>sh skills run ${skill.name}:${skill.commands[0]?.name || 'command'}</code>
                        <button class="copy-btn" data-code="sh skills run ${skill.name}:${skill.commands[0]?.name || 'command'}">复制</button>
                    </div>
                `;
            } else if (tabName === 'permissions') {
                const permissionDescriptions = {
                    'file:read': { desc: '读取文件', icon: '📄', sensitive: false },
                    'file:write': { desc: '写入文件', icon: '📝', sensitive: false },
                    'data:read': { desc: '读取客户数据', icon: '👁', sensitive: false },
                    'data:write': { desc: '修改客户数据', icon: '✏️', sensitive: true },
                    'network:local': { desc: '本地网络访问', icon: '🔗', sensitive: false },
                    'network:internet': { desc: '互联网访问', icon: '🌐', sensitive: true },
                    'config:read': { desc: '读取配置', icon: '⚙️', sensitive: false },
                    'config:write': { desc: '修改配置', icon: '🔧', sensitive: true },
                    'execute': { desc: '执行外部命令', icon: '⚡', sensitive: true }
                };

                content.innerHTML = `
                    <h3>所需权限</h3>
                    <p style="margin-bottom: 16px; color: var(--text-secondary);">该技能需要以下权限才能正常运行：</p>
                    <div class="permissions-list">
                        ${skill.permissions.map(perm => {
                            const info = permissionDescriptions[perm] || { desc: perm, icon: '🔒', sensitive: false };
                            return `
                                <span class="permission-badge ${info.sensitive ? 'sensitive' : ''}">
                                    <span>${info.icon}</span>
                                    ${info.desc}
                                </span>
                            `;
                        }).join('')}
                    </div>
                    ${skill.permissions.some(p => permissionDescriptions[p]?.sensitive) ? `
                        <p style="margin-top: 16px; font-size: 13px; color: var(--warning);">
                            ⚠️ 此技能包含敏感权限，安装时将提示确认
                        </p>
                    ` : ''}
                `;
            }
        });
    });

    skillModal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

// Close Skill Modal
function closeSkillModal() {
    skillModal.classList.remove('active');
    document.body.style.overflow = '';
}

// Copy Install Command
function copyInstallCommand(skillName) {
    const command = `sh skills install ${skillName}`;
    navigator.clipboard.writeText(command).then(() => {
        const btn = document.querySelector('.skill-detail-actions .btn-primary');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            已复制安装命令!
        `;
        btn.style.background = 'var(--success)';

        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.style.background = '';
        }, 2000);
    });
}

// Update stats in hero
function updateHeroStats() {
    const totalDownloads = SKILLS_DATA.reduce((sum, s) => sum + s.downloads, 0);
    document.querySelector('.hero-stats .stat-number').textContent = SKILLS_DATA.length;
}

// Initial stats update
updateHeroStats();

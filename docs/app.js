const DEFAULT_API_BASE = "https://skills-store-backend.onrender.com";

const state = {
    apiBase: localStorage.getItem("skillsStoreApiBase") || DEFAULT_API_BASE,
    token: localStorage.getItem("skillsStoreToken") || "",
    user: JSON.parse(localStorage.getItem("skillsStoreUser") || "null"),
    skills: [],
    featured: [],
    categories: [],
    reviews: [],
    adminStats: null,
};

const page = document.body.dataset.page || "store";
const els = {};

const CATEGORY_META = {
    all: {
        className: "all",
        label: "All",
        svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>',
    },
    data: {
        className: "data",
        label: "Data",
        svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"></path><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"></path><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"></path></svg>',
    },
    analytics: {
        className: "analytics",
        label: "Analytics",
        svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"></path><path d="m19 9-5 5-4-4-3 3"></path></svg>',
    },
    marketing: {
        className: "marketing",
        label: "Marketing",
        svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"></path><rect x="2" y="4" width="20" height="16" rx="2"></rect></svg>',
    },
    integration: {
        className: "integration",
        label: "Integration",
        svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22v-5"></path><path d="M9 8V2"></path><path d="M15 8V2"></path><path d="M12 8a4 4 0 0 0-4 4v1a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-1a4 4 0 0 0-4-4Z"></path></svg>',
    },
    utility: {
        className: "utility",
        label: "Utility",
        svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>',
    },
};

document.addEventListener("DOMContentLoaded", () => {
    bindCommonElements();
    bindCommonEvents();
    initializePage().catch((error) => {
        console.error(error);
        showToast(error.message || "Failed to initialize page.", true);
    });
});

function bindCommonElements() {
    els.toast = document.getElementById("toast");
    els.logoutButtons = document.querySelectorAll("[data-action='logout']");
    els.apiBaseDisplays = document.querySelectorAll("[data-api-base]");
    els.userNameDisplays = document.querySelectorAll("[data-user-name]");
    els.userRoleDisplays = document.querySelectorAll("[data-user-role]");
    els.tabButtons = document.querySelectorAll("[data-tab-target]");
    els.tabPanels = document.querySelectorAll("[data-tab-panel]");
    els.cliButton = document.getElementById("cliBtn");
    els.cliModal = document.getElementById("cliModal");
    els.cliModalClose = document.getElementById("cliModalClose");
}

function bindCommonEvents() {
    els.logoutButtons.forEach((button) => {
        button.addEventListener("click", () => logout(true));
    });
    els.tabButtons.forEach((button) => {
        button.addEventListener("click", () => activateTab(button.dataset.tabTarget));
    });
    if (els.cliButton && els.cliModal) {
        els.cliButton.addEventListener("click", () => {
            els.cliModal.classList.add("active");
        });
    }
    if (els.cliModalClose && els.cliModal) {
        els.cliModalClose.addEventListener("click", () => {
            els.cliModal.classList.remove("active");
        });
        els.cliModal.querySelector(".modal-overlay")?.addEventListener("click", () => {
            els.cliModal.classList.remove("active");
        });
    }
    document.addEventListener("click", async (event) => {
        const saveButton = event.target.closest("[data-save-skill]");
        if (saveButton) {
            const skillName = saveButton.dataset.saveSkill;
            const saved = toggleSavedSkill(skillName);
            if (page === "user") {
                renderUserSkills();
            } else if (page === "store") {
                renderCatalog();
            } else if (page === "skill") {
                const skill = state.skills.find((item) => item.name === skillName);
                const params = new URLSearchParams(window.location.search);
                if (skill && params.get("name") === skillName) {
                    const versions = await apiFetch(`/api/v1/skills/${encodeURIComponent(skillName)}/versions`);
                    let downloadInfo = null;
                    try {
                        downloadInfo = await apiFetch(`/api/v1/skills/${encodeURIComponent(skillName)}/download-info`);
                    } catch {
                        downloadInfo = null;
                    }
                    renderSkillDetailPage(skill, versions, downloadInfo);
                }
            }
            showToast(saved ? "Added to My skills." : "Removed from My skills.");
            return;
        }
        const button = event.target.closest("[data-copy-text]");
        if (!button) {
            return;
        }
        try {
            await navigator.clipboard.writeText(button.dataset.copyText || "");
            showToast("Command copied.");
        } catch {
            showToast("Copy failed.", true);
        }
    });
}

async function initializePage() {
    renderHeaderState();
    switch (page) {
        case "store":
            await initStorePage();
            break;
        case "skill":
            await initSkillPage();
            break;
        case "login":
        case "developer-login":
        case "admin-login":
            await initLoginPage();
            break;
        case "register":
            await initRegisterPage();
            break;
        case "developer":
            await initDeveloperPage();
            break;
        case "user":
            await initUserPage();
            break;
        case "admin":
            await initAdminPage();
            break;
        default:
            break;
    }
}

function getApiUrl(path) {
    return `${state.apiBase}${path}`;
}

async function apiFetch(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    if (state.token) {
        headers.set("Authorization", `Bearer ${state.token}`);
    }

    const response = await fetch(getApiUrl(path), {
        ...options,
        headers,
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();

    if (!response.ok) {
        const detail = payload?.detail?.error || payload?.error;
        throw new Error(detail?.message || response.statusText || "Request failed");
    }
    return payload.data ?? payload;
}

function setSession(token, user) {
    state.token = token;
    state.user = user;
    localStorage.setItem("skillsStoreToken", token);
    localStorage.setItem("skillsStoreUser", JSON.stringify(user));
    renderHeaderState();
}

function logout(showMessage) {
    state.token = "";
    state.user = null;
    localStorage.removeItem("skillsStoreToken");
    localStorage.removeItem("skillsStoreUser");
    renderHeaderState();
    if (showMessage) {
        showToast("Signed out.");
    }
    if (page === "developer" || page === "admin") {
        window.location.href = page === "admin" ? "admin-login.html" : "login.html";
    }
}

async function loadCurrentUser() {
    if (!state.token) {
        state.user = null;
        renderHeaderState();
        return null;
    }
    try {
        state.user = await apiFetch("/api/v1/auth/me");
        localStorage.setItem("skillsStoreUser", JSON.stringify(state.user));
        renderHeaderState();
        return state.user;
    } catch {
        logout(false);
        return null;
    }
}

function renderHeaderState() {
    const userName = state.user?.name || "Guest";
    const userRole = state.user?.role || "Visitor";
    els.apiBaseDisplays.forEach((el) => {
        el.textContent = state.apiBase;
    });
    els.userNameDisplays.forEach((el) => {
        el.textContent = userName;
    });
    els.userRoleDisplays.forEach((el) => {
        el.textContent = userRole;
    });
}

function activateTab(tabName) {
    els.tabButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.tabTarget === tabName);
    });
    els.tabPanels.forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.tabPanel === tabName);
    });
}

function showToast(message, isError = false) {
    if (!els.toast) {
        return;
    }
    els.toast.textContent = message;
    els.toast.className = `console-toast show${isError ? " error" : ""}`;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
        els.toast.className = "console-toast";
    }, 2600);
}

async function initStorePage() {
    els.featuredList = document.getElementById("featuredSkills");
    els.catalogList = document.getElementById("catalogSkills");
    els.searchInput = document.getElementById("searchInput");
    els.categorySelect = document.getElementById("categorySelect");
    els.categoryChips = document.getElementById("categoryChips");
    els.catalogResultCount = document.getElementById("catalogResultCount");
    els.heroCount = document.getElementById("heroSkillCount");
    els.featuredCount = document.getElementById("featuredCount");
    els.sortSelect = document.getElementById("sortSelect");

    els.searchInput.addEventListener("input", renderCatalog);
    els.categorySelect.addEventListener("change", renderCatalog);
    if (els.sortSelect) {
        els.sortSelect.addEventListener("change", renderCatalog);
    }

    await Promise.all([loadCategories(), loadFeaturedSkills(), loadSkills()]);
    renderCatalog();
}

async function initSkillPage() {
    const params = new URLSearchParams(window.location.search);
    const skillName = params.get("name");
    if (!skillName) {
        throw new Error("Missing skill name.");
    }

    const skill = await apiFetch(`/api/v1/skills/${encodeURIComponent(skillName)}`);
    const versions = await apiFetch(`/api/v1/skills/${encodeURIComponent(skillName)}/versions`);
    let downloadInfo = null;
    try {
        downloadInfo = await apiFetch(`/api/v1/skills/${encodeURIComponent(skillName)}/download-info`);
    } catch {
        downloadInfo = null;
    }

    if (!state.skills.find((item) => item.name === skill.name)) {
        state.skills.push(skill);
    }

    renderSkillDetailPage(skill, versions, downloadInfo);
}

async function initLoginPage() {
    const existing = await loadCurrentUser();
    if (existing) {
        if (page === "login") {
            window.location.href = "user.html";
            return;
        }
        redirectByRole(existing.role);
        return;
    }

    const form = document.getElementById("loginForm");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const payload = Object.fromEntries(new FormData(form));
            const data = await apiFetch("/api/v1/auth/login", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            setSession(data.access_token, data.user);
            if (page === "admin-login" && data.user.role !== "store_admin") {
                logout(false);
                throw new Error("This entry point is for store admin accounts only.");
            }
            if (page === "developer-login" && data.user.role !== "developer") {
                logout(false);
                throw new Error("This entry point is for developer accounts only.");
            }
            showToast("Signed in.");
            if (page === "login") {
                window.location.href = "user.html";
                return;
            }
            redirectByRole(data.user.role);
        } catch (error) {
            showToast(error.message, true);
        }
    });
}

async function initRegisterPage() {
    const form = document.getElementById("registerForm");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const payload = Object.fromEntries(new FormData(form));
            await apiFetch("/api/v1/auth/register", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            showToast("Account created. Please sign in.");
            window.setTimeout(() => {
                window.location.href = "developer-login.html";
            }, 800);
        } catch (error) {
            showToast(error.message, true);
        }
    });
}

async function initDeveloperPage() {
    const user = await requireRole("developer");
    if (!user) {
        return;
    }

    els.profileForm = document.getElementById("profileForm");
    els.createSkillForm = document.getElementById("createSkillForm");
    els.uploadVersionForm = document.getElementById("uploadVersionForm");
    els.developerCategorySelect = document.getElementById("developerCategorySelect");
    els.developerSkillsBody = document.getElementById("developerSkillsBody");
    els.profileName = document.getElementById("profileName");
    els.profileEmail = document.getElementById("profileEmail");
    els.profileRole = document.getElementById("profileRole");

    populateProfile(user);
    els.profileForm.addEventListener("submit", handleProfileUpdate);
    els.createSkillForm.addEventListener("submit", handleCreateSkill);
    els.uploadVersionForm.addEventListener("submit", handleUploadVersion);

    await Promise.all([loadCategories(), loadDeveloperSkills(), loadSkills()]);
}

async function initUserPage() {
    const user = await loadCurrentUser();
    if (!user) {
        window.location.href = "login.html";
        return;
    }

    els.profileName = document.getElementById("profileName");
    els.profileEmail = document.getElementById("profileEmail");
    els.profileRole = document.getElementById("profileRole");
    els.userSkillList = document.getElementById("userSkillList");
    els.userIdentitySummary = document.getElementById("userIdentitySummary");

    populateProfile(user);
    if (els.userIdentitySummary) {
        els.userIdentitySummary.textContent = `${user.name || "Store user"} is signed in with ${user.email}.`;
    }

    await loadSkills();
    if (els.userSkillList) {
        const suggested = state.skills.slice(0, 3);
        els.userSkillList.innerHTML = suggested.length
            ? suggested.map((skill) => `
                <article class="dash-card">
                    <div class="dash-card-head">
                        <div>
                            <h3>${escapeHtml(skill.display_name || skill.name)}</h3>
                            <p>${escapeHtml(skill.summary || "No summary provided.")}</p>
                        </div>
                        <span class="status-chip">${skill.status === "active" ? "Enabled" : "Disabled"}</span>
                    </div>
                    <p class="dash-meta">Latest version: ${escapeHtml(skill.latest_version || "n/a")} | Downloads: ${escapeHtml(String(skill.download_count || 0))}</p>
                    <div class="dash-actions">
                        <a class="btn btn-outline btn-sm" href="skill.html?name=${encodeURIComponent(skill.name)}">Open detail page</a>
                    </div>
                </article>
            `).join("")
            : emptyState("No suggested skills yet.");
    }
    renderUserSkills();
}

function getUserSkillOverrides() {
    return JSON.parse(localStorage.getItem("skillsStoreUserSkillStates") || "{}");
}

function getSavedSkillNames() {
    return JSON.parse(localStorage.getItem("skillsStoreSavedSkills") || "[]");
}

function isSkillSaved(skillName) {
    return getSavedSkillNames().includes(skillName);
}

function toggleSavedSkill(skillName) {
    const saved = new Set(getSavedSkillNames());
    if (saved.has(skillName)) {
        saved.delete(skillName);
        localStorage.setItem("skillsStoreSavedSkills", JSON.stringify([...saved]));
        return false;
    }
    saved.add(skillName);
    localStorage.setItem("skillsStoreSavedSkills", JSON.stringify([...saved]));
    return true;
}

function setUserSkillOverride(skillName, enabled) {
    const overrides = getUserSkillOverrides();
    overrides[skillName] = enabled ? "enabled" : "disabled";
    localStorage.setItem("skillsStoreUserSkillStates", JSON.stringify(overrides));
}

function getUserSkillEnabled(skill) {
    const overrides = getUserSkillOverrides();
    if (overrides[skill.name]) {
        return overrides[skill.name] === "enabled";
    }
    return skill.status === "active";
}

function renderUserSkills() {
    if (!els.userSkillList) {
        return;
    }
    const savedNames = getSavedSkillNames();
    const suggested = savedNames.length
        ? savedNames.map((name) => state.skills.find((item) => item.name === name)).filter(Boolean)
        : state.skills.slice(0, 3);
    els.userSkillList.innerHTML = suggested.length
        ? suggested.map((skill) => {
            const enabled = getUserSkillEnabled(skill);
            return `
                <article class="dash-card">
                    <div class="dash-card-head">
                        <div>
                            <h3>${escapeHtml(skill.display_name || skill.name)}</h3>
                            <p>${escapeHtml(skill.summary || "No summary provided.")}</p>
                        </div>
                        <button class="status-chip status-toggle${enabled ? " enabled" : " disabled"}" type="button" data-skill-toggle="${escapeHtml(skill.name)}">
                            ${enabled ? "Enabled" : "Disabled"}
                        </button>
                    </div>
                    <p class="dash-meta">Latest version: ${escapeHtml(skill.latest_version || "n/a")} · Downloads: ${escapeHtml(String(skill.download_count || 0))}</p>
                    <div class="dash-actions">
                        <button class="btn btn-secondary btn-sm" type="button" data-save-skill="${escapeHtml(skill.name)}">Remove from My skills</button>
                        <a class="btn btn-outline btn-sm" href="skill.html?name=${encodeURIComponent(skill.name)}">Open detail page</a>
                    </div>
                </article>
            `;
        }).join("")
        : emptyState("No saved skills yet. Add skills from the catalog or a detail page.");

    els.userSkillList.querySelectorAll("[data-skill-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
            const skillName = button.dataset.skillToggle;
            const skill = state.skills.find((item) => item.name === skillName);
            if (!skill) {
                return;
            }
            const nextEnabled = !getUserSkillEnabled(skill);
            setUserSkillOverride(skillName, nextEnabled);
            renderUserSkills();
            showToast(`Skill ${nextEnabled ? "enabled" : "disabled"}.`);
        });
    });
    els.userSkillList.querySelectorAll("[data-save-skill]").forEach((button) => {
        button.addEventListener("click", () => {
            toggleSavedSkill(button.dataset.saveSkill);
            renderUserSkills();
            showToast("Removed from My skills.");
        });
    });
}

async function initAdminPage() {
    const user = await requireRole("store_admin");
    if (!user) {
        return;
    }

    els.reviewStatusFilter = document.getElementById("reviewStatusFilter");
    els.reviewsList = document.getElementById("reviewsList");
    els.adminStats = document.getElementById("adminStats");
    els.revokeForm = document.getElementById("revokeForm");
    els.profileName = document.getElementById("profileName");
    els.profileEmail = document.getElementById("profileEmail");
    els.profileRole = document.getElementById("profileRole");

    populateProfile(user);
    els.reviewStatusFilter.addEventListener("change", loadReviews);
    els.revokeForm.addEventListener("submit", handleRevoke);

    await Promise.all([loadReviews(), loadAdminStats()]);
}

async function requireRole(role) {
    const user = await loadCurrentUser();
    if (!user) {
        window.location.href = role === "store_admin" ? "admin-login.html" : "login.html";
        return null;
    }
    if (user.role !== role) {
        redirectByRole(user.role);
        return null;
    }
    return user;
}

function redirectByRole(role) {
    if (role === "store_admin") {
        window.location.href = "admin.html";
        return;
    }
    if (role === "developer") {
        window.location.href = "developer.html";
        return;
    }
    window.location.href = "user.html";
}

function populateProfile(user) {
    if (els.profileName) {
        els.profileName.textContent = user.name || "Unknown";
    }
    if (els.profileEmail) {
        els.profileEmail.textContent = user.email;
    }
    if (els.profileRole) {
        els.profileRole.textContent = user.role;
    }
    if (els.profileForm) {
        els.profileForm.elements.name.value = user.name || "";
        els.profileForm.elements.bio.value = user.bio || "";
        els.profileForm.elements.website.value = user.website || "";
    }
}

async function loadCategories() {
    state.categories = await apiFetch("/api/v1/categories");
    if (els.categorySelect) {
        els.categorySelect.innerHTML = ['<option value="">All categories</option>']
            .concat(state.categories.map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`))
            .join("");
    }
    if (els.categoryChips) {
        els.categoryChips.innerHTML = [
            `<button class="category-chip active" type="button" data-category-chip="">
                ${CATEGORY_META.all.svg}
                <span>${escapeHtml(CATEGORY_META.all.label)}</span>
            </button>`,
            ...state.categories.map((item) => (
                `<button class="category-chip" type="button" data-category-chip="${escapeHtml(item.key)}">
                    ${(CATEGORY_META[item.key] || CATEGORY_META.all).svg}
                    <span>${escapeHtml(item.label)}</span>
                </button>`
            )),
        ].join("");
        els.categoryChips.querySelectorAll("[data-category-chip]").forEach((button) => {
            button.addEventListener("click", () => {
                els.categorySelect.value = button.dataset.categoryChip || "";
                renderCatalog();
            });
        });
    }
    if (els.developerCategorySelect) {
        els.developerCategorySelect.innerHTML = ['<option value="">Choose category</option>']
            .concat(state.categories.map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`))
            .join("");
    }
}

async function loadSkills() {
    const payload = await apiFetch("/api/v1/skills");
    state.skills = Array.isArray(payload) ? payload : [];
    if (els.heroCount) {
        els.heroCount.textContent = String(state.skills.length);
    }
}

async function loadFeaturedSkills() {
    state.featured = await apiFetch("/api/v1/skills/featured");
    if (els.featuredCount) {
        els.featuredCount.textContent = String(state.featured.length);
    }
    if (els.featuredList) {
        els.featuredList.innerHTML = state.featured.map(renderSkillCard).join("") || emptyState("No featured skills yet.");
        bindSkillDetails(els.featuredList);
    }
}

function renderCatalog() {
    if (!els.catalogList) {
        return;
    }
    const term = (els.searchInput?.value || "").trim().toLowerCase();
    const category = els.categorySelect?.value || "";
    const sortBy = els.sortSelect?.value || "downloads";
    const filtered = state.skills.filter((item) => {
        const matchesCategory = !category || item.category === category;
        const haystack = [item.name, item.display_name, item.summary].join(" ").toLowerCase();
        const matchesSearch = !term || haystack.includes(term);
        return matchesCategory && matchesSearch;
    });
    filtered.sort((a, b) => {
        if (sortBy === "name") {
            return String(a.display_name || a.name).localeCompare(String(b.display_name || b.name));
        }
        if (sortBy === "version") {
            return String(b.latest_version || "").localeCompare(String(a.latest_version || ""));
        }
        return Number(b.download_count || 0) - Number(a.download_count || 0);
    });
    if (els.catalogResultCount) {
        els.catalogResultCount.textContent = `${filtered.length} skill${filtered.length === 1 ? "" : "s"}`;
    }
    if (els.categoryChips) {
        els.categoryChips.querySelectorAll("[data-category-chip]").forEach((button) => {
            button.classList.toggle("active", (button.dataset.categoryChip || "") === category);
        });
    }
    els.catalogList.innerHTML = filtered.map(renderSkillCard).join("") || emptyState("No skills match the current filter.");
    bindSkillDetails(els.catalogList);
}

async function loadDeveloperSkills() {
    const data = await apiFetch("/api/v1/developer/skills");
    els.developerSkillsBody.innerHTML = data.map((skill) => `
        <tr>
            <td>${escapeHtml(skill.display_name || skill.name)}</td>
            <td>${escapeHtml(skill.category || "-")}</td>
            <td>${escapeHtml(skill.latest_version || "-")}</td>
            <td>${escapeHtml(skill.status || "-")}</td>
            <td>${escapeHtml(String(skill.download_count || 0))}</td>
        </tr>
    `).join("") || '<tr><td colspan="5">No skills yet.</td></tr>';
}

async function loadReviews() {
    const filter = els.reviewStatusFilter?.value || "";
    const query = filter ? `?status=${encodeURIComponent(filter)}` : "";
    const payload = await apiFetch(`/api/v1/admin/reviews${query}`);
    state.reviews = Array.isArray(payload) ? payload : [];
    els.reviewsList.innerHTML = state.reviews.map((review) => `
        <article class="dash-card review-card">
            <div class="dash-card-head">
                <div>
                    <h3>${escapeHtml(review.display_name || review.skill_name)}</h3>
                    <p>${escapeHtml(review.skill_name)} · ${escapeHtml(review.version)}</p>
                </div>
                <span class="status-chip">${escapeHtml(review.status)}</span>
            </div>
            <p class="dash-meta">Developer: ${escapeHtml((review.developer && review.developer.name) || "Unknown")}</p>
            <p class="dash-meta">Scan: ${escapeHtml((review.scan_summary && review.scan_summary.status) || "pending")}</p>
            <div class="dash-actions">
                <button class="btn btn-outline btn-sm" data-review-action="start" data-review-id="${review.id}">Start</button>
                <button class="btn btn-primary btn-sm" data-review-action="approve" data-review-id="${review.id}">Approve</button>
                <button class="btn btn-secondary btn-sm" data-review-action="reject" data-review-id="${review.id}">Reject</button>
            </div>
        </article>
    `).join("") || emptyState("No review items found.");

    els.reviewsList.querySelectorAll("[data-review-action]").forEach((button) => {
        button.addEventListener("click", async () => {
            const action = button.dataset.reviewAction;
            const reviewId = button.dataset.reviewId;
            const comment = window.prompt(`Optional comment for ${action}:`, "");
            if (comment === null) {
                return;
            }
            try {
                await apiFetch(`/api/v1/admin/reviews/${reviewId}/${action}`, {
                    method: "POST",
                    body: JSON.stringify({ comment }),
                });
                showToast(`Review ${action}ed.`);
                await Promise.all([loadReviews(), loadAdminStats()]);
            } catch (error) {
                showToast(error.message, true);
            }
        });
    });
}

async function loadAdminStats() {
    const stats = await apiFetch("/api/v1/admin/stats");
    els.adminStats.innerHTML = Object.entries(stats).map(([key, value]) => `
        <div class="metric-card">
            <span>${escapeHtml(key.replaceAll("_", " "))}</span>
            <strong>${escapeHtml(String(value))}</strong>
        </div>
    `).join("");
}

async function handleProfileUpdate(event) {
    event.preventDefault();
    try {
        const payload = Object.fromEntries(new FormData(event.currentTarget));
        const user = await apiFetch("/api/v1/auth/me", {
            method: "PATCH",
            body: JSON.stringify(payload),
        });
        state.user = user;
        localStorage.setItem("skillsStoreUser", JSON.stringify(user));
        populateProfile(user);
        renderHeaderState();
        showToast("Profile updated.");
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleCreateSkill(event) {
    event.preventDefault();
    try {
        const payload = Object.fromEntries(new FormData(event.currentTarget));
        payload.tags = payload.tags
            ? payload.tags.split(",").map((item) => item.trim()).filter(Boolean)
            : [];
        await apiFetch("/api/v1/developer/skills", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        showToast("Skill created.");
        event.currentTarget.reset();
        await loadDeveloperSkills();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleUploadVersion(event) {
    event.preventDefault();
    try {
        const formData = new FormData(event.currentTarget);
        const skillName = formData.get("skill_name");
        formData.delete("skill_name");
        await apiFetch(`/api/v1/developer/skills/${encodeURIComponent(skillName)}/versions`, {
            method: "POST",
            body: formData,
        });
        showToast("Version submitted for review.");
        event.currentTarget.reset();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleRevoke(event) {
    event.preventDefault();
    try {
        const formData = new FormData(event.currentTarget);
        const certificateSerial = formData.get("certificate_serial");
        await apiFetch(`/api/v1/admin/certifications/${encodeURIComponent(certificateSerial)}/revoke`, {
            method: "POST",
            body: JSON.stringify({ comment: formData.get("comment") }),
        });
        showToast("Certificate revoked.");
        event.currentTarget.reset();
    } catch (error) {
        showToast(error.message, true);
    }
}

function renderSkillCard(skill) {
    const categoryMeta = CATEGORY_META[skill.category] || CATEGORY_META.all;
    return `
        <article class="skill-card">
            <div class="skill-card-top">
                <span class="status-chip">${escapeHtml(skill.category || "unknown")}</span>
                <span class="skill-downloads">${escapeHtml(String(skill.download_count || 0))} downloads</span>
            </div>
            <div class="skill-card-headline">
                <div class="skill-icon ${escapeHtml(categoryMeta.className)}">${categoryMeta.svg}</div>
                <div class="skill-card-title">
                    <h3>${escapeHtml(skill.display_name || skill.name)}</h3>
                    <p class="skill-card-slug">${escapeHtml(skill.name)}</p>
                </div>
            </div>
            <p class="skill-summary">${escapeHtml(skill.summary || "No summary provided.")}</p>
            <div class="skill-card-foot">
                <span>${escapeHtml(skill.latest_version || "No version")}</span>
                <button class="btn btn-secondary btn-sm" type="button" data-save-skill="${escapeHtml(skill.name)}">${isSkillSaved(skill.name) ? "Saved" : "Add to My skills"}</button>
                <a class="btn btn-outline btn-sm" href="skill.html?name=${encodeURIComponent(skill.name)}">View details</a>
            </div>
        </article>
    `;
}

function bindSkillDetails(scope) {
    return scope;
}

function emptyState(message) {
    return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderSkillDetailPage(skill, versions, downloadInfo) {
    const latestInstallCommand = `socialhub skills install ${skill.name}`;
    const pinnedInstallCommand = `socialhub skills install ${skill.name}@${(skill.latest_version || "1.0.0")}`;

    document.getElementById("skillName").textContent = skill.display_name || skill.name;
    document.getElementById("skillSlug").textContent = skill.name;
    document.getElementById("skillSummary").textContent = skill.summary || "";
    document.getElementById("skillDescription").textContent = skill.description || "";
    document.getElementById("skillTags").innerHTML = (skill.tags || []).map((tag) => `<span class="status-chip">${escapeHtml(tag)}</span>`).join("") || emptyState("No tags");

    document.getElementById("detailHeroMeta").innerHTML = `
        <span class="detail-meta-item">Category: ${escapeHtml(skill.category || "unknown")}</span>
        <span class="detail-meta-item">Latest version: ${escapeHtml(skill.latest_version || "n/a")}</span>
        <span class="detail-meta-item">Downloads: ${escapeHtml(String(skill.download_count || 0))}</span>
    `;
    document.getElementById("detailHeroActions").innerHTML = `
        <button class="btn btn-primary btn-lg" type="button" data-copy-text="${escapeHtml(latestInstallCommand)}">Copy install command</button>
        <button class="btn btn-secondary btn-lg" type="button" data-save-skill="${escapeHtml(skill.name)}">${isSkillSaved(skill.name) ? "Saved to My skills" : "Add to My skills"}</button>
        <a class="btn btn-outline btn-lg" href="#versions">Review versions</a>
    `;
    document.getElementById("installSummaryPanel").innerHTML = `
        <p class="detail-side-card-text">Install this skill from the SocialHub CLI instead of downloading an archive manually.</p>
        ${renderCommandBlock(latestInstallCommand)}
        <div class="detail-mini-list">
            <div><span>Latest release</span><strong>${escapeHtml(skill.latest_version || "n/a")}</strong></div>
            <div><span>Publisher</span><strong>${escapeHtml(skill.developer?.name || "Unknown")}</strong></div>
            <div><span>Package metadata</span><strong>${downloadInfo ? "Available" : "Pending"}</strong></div>
        </div>
    `;

    document.getElementById("trustPanel").innerHTML = `
        <div class="trust-row"><span>Publisher</span><strong>${escapeHtml(skill.developer?.name || "Unknown")}</strong></div>
        <div class="trust-row"><span>Status</span><strong>${escapeHtml(skill.status || "active")}</strong></div>
        <div class="trust-row"><span>Latest version</span><strong>${escapeHtml(skill.latest_version || "n/a")}</strong></div>
        <div class="trust-row"><span>License</span><strong>${escapeHtml(skill.license_name || "Not specified")}</strong></div>
        <div class="trust-row"><span>CLI install</span><strong>${downloadInfo ? "Ready" : "Check release data"}</strong></div>
    `;

    document.getElementById("packagePanel").innerHTML = downloadInfo
        ? `
            <div class="trust-row"><span>Install command</span><strong class="mono">${escapeHtml(latestInstallCommand)}</strong></div>
            <div class="trust-row"><span>Package hash</span><strong class="mono">${escapeHtml(downloadInfo.package_hash)}</strong></div>
            <div class="trust-row"><span>Package size</span><strong>${escapeHtml(String(downloadInfo.package_size))} bytes</strong></div>
            <div class="trust-row"><span>Certificate</span><strong>${escapeHtml(downloadInfo.certificate_serial || "Not issued")}</strong></div>
            <div class="trust-row"><span>Public key</span><strong>${escapeHtml(downloadInfo.public_key_id || "n/a")}</strong></div>
        `
        : emptyState("Package metadata is not available yet.");

    document.getElementById("securityPanel").innerHTML = renderInfoCards(
        skill.security_review,
        [
            {
                title: "Security posture",
                body: "This release is presented as a reviewed catalog artifact. The package metadata, release lineage, and certificate identifiers are visible in this page layout.",
            },
        ],
    );

    document.getElementById("runtimePanel").innerHTML = renderInfoCards(
        skill.runtime_requirements,
        [
            {
                title: "Required runtime",
                items: [
                    "Compatible SocialHub CLI environment",
                    "Network access required by the workflow this skill performs",
                    "Ability to load the packaged skill bundle and its manifest",
                ],
            },
        ],
    );

    document.getElementById("installPanel").innerHTML = renderInstallCards(skill, latestInstallCommand, pinnedInstallCommand);

    document.getElementById("filesPanel").innerHTML = renderInfoCards(
        skill.docs_sections,
        [
            {
                title: "Included documentation",
                body: "This layout reserves room for README content, usage notes, file manifests, and installation instructions once the backend exposes them in a richer form.",
            },
        ],
    );

    document.getElementById("versionsPanel").innerHTML = versions.length
        ? versions.map((item) => `
            <article class="version-card">
                <div class="version-card-head">
                    <strong>${escapeHtml(item.version)}</strong>
                    <span class="status-chip">${escapeHtml(item.status)}</span>
                </div>
                <p>${escapeHtml(item.release_notes || "No release notes provided.")}</p>
                <div class="version-card-meta">
                    <span>Hash: ${escapeHtml(item.package_hash)}</span>
                    <span>Size: ${escapeHtml(String(item.package_size))} bytes</span>
                    <span>Published: ${formatDate(item.published_at)}</span>
                </div>
                <div class="version-card-actions">
                    ${renderCommandBlock(`socialhub skills install ${skill.name}@${item.version}`)}
                </div>
            </article>
        `).join("")
        : emptyState("No versions published yet.");
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function renderCommandBlock(command) {
    const escaped = escapeHtml(command);
    return `
        <div class="code-block">
            <code>${escaped}</code>
            <button class="copy-btn" type="button" data-copy-text="${escaped}">Copy</button>
        </div>
    `;
}

function renderInfoCards(items, fallback) {
    const source = Array.isArray(items) && items.length ? items : fallback;
    return source.map((item) => {
        const title = escapeHtml(item.title || "Details");
        const body = item.body ? `<p>${escapeHtml(item.body)}</p>` : "";
        const list = Array.isArray(item.items) && item.items.length
            ? `<ul class="content-list">${item.items.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>`
            : "";
        return `
            <article class="content-card">
                <h3>${title}</h3>
                ${body}
                ${list}
            </article>
        `;
    }).join("");
}

function renderInstallCards(skill, latestInstallCommand, pinnedInstallCommand) {
    const guidance = Array.isArray(skill.install_guidance) && skill.install_guidance.length
        ? skill.install_guidance
        : [
            {
                title: "Install the latest published release",
                body: "Copy the command below and run it inside the SocialHub CLI.",
                command: latestInstallCommand,
            },
            {
                title: "Pin a specific version",
                body: "Use a version-pinned install for deterministic rollouts.",
                command: pinnedInstallCommand,
            },
        ];

    const cards = guidance.map((item) => `
        <article class="content-card">
            <h3>${escapeHtml(item.title || "Install")}</h3>
            <p>${escapeHtml(item.body || "")}</p>
            ${item.command ? renderCommandBlock(item.command) : ""}
        </article>
    `);

    cards.push(`
        <article class="content-card">
            <h3>What to validate before install</h3>
            <ul class="content-list">
                <li>Publisher identity matches your approval policy</li>
                <li>Latest version is the intended release</li>
                <li>Package metadata and certificate data are present</li>
                <li>The CLI environment already has access to the target store endpoint</li>
            </ul>
        </article>
    `);
    return cards.join("");
}

function formatDate(value) {
    if (!value) {
        return "Not published";
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Not published" : date.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
    });
}

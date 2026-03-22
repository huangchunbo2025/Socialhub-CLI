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

const els = {};

document.addEventListener("DOMContentLoaded", () => {
    bindElements();
    bindEvents();
    initializeView();
});

function bindElements() {
    els.apiBaseInput = document.getElementById("apiBaseInput");
    els.saveApiBtn = document.getElementById("saveApiBtn");
    els.apiStatusPill = document.getElementById("apiStatusPill");
    els.apiStatusText = document.getElementById("apiStatusText");
    els.refreshBtn = document.getElementById("refreshBtn");
    els.logoutBtn = document.getElementById("logoutBtn");
    els.searchInput = document.getElementById("searchInput");
    els.categorySelect = document.getElementById("categorySelect");
    els.featuredSkills = document.getElementById("featuredSkills");
    els.skillsList = document.getElementById("skillsList");
    els.featuredMeta = document.getElementById("featuredMeta");
    els.skillsMeta = document.getElementById("skillsMeta");
    els.statsSkills = document.getElementById("statsSkills");
    els.statsFeatured = document.getElementById("statsFeatured");
    els.statsReviews = document.getElementById("statsReviews");
    els.registerForm = document.getElementById("registerForm");
    els.loginForm = document.getElementById("loginForm");
    els.profileForm = document.getElementById("profileForm");
    els.currentUserCard = document.getElementById("currentUserCard");
    els.userRole = document.getElementById("userRole");
    els.createSkillForm = document.getElementById("createSkillForm");
    els.uploadVersionForm = document.getElementById("uploadVersionForm");
    els.developerCategorySelect = document.getElementById("developerCategorySelect");
    els.developerSkillsBody = document.getElementById("developerSkillsBody");
    els.developerSkillsMeta = document.getElementById("developerSkillsMeta");
    els.reviewStatusFilter = document.getElementById("reviewStatusFilter");
    els.reviewsList = document.getElementById("reviewsList");
    els.reviewsMeta = document.getElementById("reviewsMeta");
    els.adminStats = document.getElementById("adminStats");
    els.revokeForm = document.getElementById("revokeForm");
    els.modal = document.getElementById("skillModal");
    els.modalBody = document.getElementById("modalBody");
    els.modalClose = document.getElementById("modalClose");
    els.toast = document.getElementById("toast");
}

function bindEvents() {
    els.saveApiBtn.addEventListener("click", saveApiBase);
    els.refreshBtn.addEventListener("click", refreshAll);
    els.logoutBtn.addEventListener("click", () => logout(true));
    els.searchInput.addEventListener("input", renderSkills);
    els.categorySelect.addEventListener("change", renderSkills);
    els.registerForm.addEventListener("submit", handleRegister);
    els.loginForm.addEventListener("submit", handleLogin);
    els.profileForm.addEventListener("submit", handleProfileUpdate);
    els.createSkillForm.addEventListener("submit", handleCreateSkill);
    els.uploadVersionForm.addEventListener("submit", handleUploadVersion);
    els.reviewStatusFilter.addEventListener("change", loadReviews);
    els.revokeForm.addEventListener("submit", handleRevoke);
    els.modalClose.addEventListener("click", closeModal);
    els.modal.querySelector(".modal-overlay").addEventListener("click", closeModal);
}

function initializeView() {
    els.apiBaseInput.value = state.apiBase;
    renderCurrentUser();
    setButtonsState();
    refreshAll();
}

function saveApiBase() {
    state.apiBase = normalizeBaseUrl(els.apiBaseInput.value);
    localStorage.setItem("skillsStoreApiBase", state.apiBase);
    showToast("API endpoint saved.");
    refreshAll();
}

function normalizeBaseUrl(value) {
    return value.trim().replace(/\/+$/, "");
}

function getApiUrl(path) {
    if (!state.apiBase) {
        throw new Error("Set the backend endpoint first.");
    }
    return `${state.apiBase}${path}`;
}

async function apiFetch(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (!(options.body instanceof FormData)) {
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

async function refreshAll() {
    setApiStatus("pending", "Checking backend health...");
    if (!state.apiBase) {
        setApiStatus("idle", "Set an API base URL, then refresh.");
        renderCategories();
        renderSkills();
        renderFeaturedSkills();
        renderDeveloperSkills([]);
        renderReviews();
        renderAdminStats();
        return;
    }
    try {
        const response = await fetch(getApiUrl("/health"));
        if (!response.ok) {
            throw new Error("Health check failed");
        }
        setApiStatus("ok", "Backend reachable.");
    } catch (error) {
        setApiStatus("error", error.message);
        return;
    }

    await Promise.allSettled([
        loadCategories(),
        loadSkills(),
        loadFeaturedSkills(),
        loadCurrentUser(),
        loadDeveloperSkills(),
        loadReviews(),
        loadAdminStats(),
    ]);
}

async function loadCategories() {
    try {
        state.categories = await apiFetch("/api/v1/categories");
    } catch {
        state.categories = [];
    }
    renderCategories();
}

async function loadSkills() {
    try {
        const payload = await apiFetch("/api/v1/skills");
        state.skills = Array.isArray(payload) ? payload : [];
    } catch {
        state.skills = [];
    }
    renderSkills();
}

async function loadFeaturedSkills() {
    try {
        state.featured = await apiFetch("/api/v1/skills/featured");
    } catch {
        state.featured = [];
    }
    renderFeaturedSkills();
}

async function loadCurrentUser() {
    if (!state.token) {
        state.user = null;
        renderCurrentUser();
        return;
    }
    try {
        state.user = await apiFetch("/api/v1/auth/me");
        localStorage.setItem("skillsStoreUser", JSON.stringify(state.user));
    } catch {
        logout(false);
    }
    renderCurrentUser();
    setButtonsState();
}

async function loadDeveloperSkills() {
    if (!state.token) {
        renderDeveloperSkills([]);
        return;
    }
    try {
        const data = await apiFetch("/api/v1/developer/skills");
        renderDeveloperSkills(data);
    } catch {
        renderDeveloperSkills([]);
    }
}

async function loadReviews() {
    if (!state.token || state.user?.role !== "store_admin") {
        state.reviews = [];
        renderReviews();
        return;
    }
    const filter = els.reviewStatusFilter.value;
    const query = filter ? `?status=${encodeURIComponent(filter)}` : "";
    try {
        const payload = await apiFetch(`/api/v1/admin/reviews${query}`);
        state.reviews = Array.isArray(payload) ? payload : [];
    } catch {
        state.reviews = [];
    }
    renderReviews();
}

async function loadAdminStats() {
    if (!state.token || state.user?.role !== "store_admin") {
        state.adminStats = null;
        renderAdminStats();
        return;
    }
    try {
        state.adminStats = await apiFetch("/api/v1/admin/stats");
    } catch {
        state.adminStats = null;
    }
    renderAdminStats();
}

async function handleRegister(event) {
    event.preventDefault();
    try {
        const payload = Object.fromEntries(new FormData(event.currentTarget));
        await apiFetch("/api/v1/auth/register", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        showToast("Account created. Sign in to continue.");
        event.currentTarget.reset();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleLogin(event) {
    event.preventDefault();
    try {
        const payload = Object.fromEntries(new FormData(event.currentTarget));
        const data = await apiFetch("/api/v1/auth/login", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        state.token = data.access_token;
        state.user = data.user;
        localStorage.setItem("skillsStoreToken", state.token);
        localStorage.setItem("skillsStoreUser", JSON.stringify(state.user));
        renderCurrentUser();
        setButtonsState();
        showToast(`Signed in as ${state.user.email}`);
        event.currentTarget.reset();
        await Promise.allSettled([loadDeveloperSkills(), loadReviews(), loadAdminStats()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleProfileUpdate(event) {
    event.preventDefault();
    if (!state.token) {
        showToast("Sign in first.", true);
        return;
    }
    try {
        const payload = Object.fromEntries(new FormData(event.currentTarget));
        const user = await apiFetch("/api/v1/auth/me", {
            method: "PATCH",
            body: JSON.stringify(payload),
        });
        state.user = user;
        localStorage.setItem("skillsStoreUser", JSON.stringify(state.user));
        renderCurrentUser();
        showToast("Profile updated.");
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleCreateSkill(event) {
    event.preventDefault();
    if (!state.token) {
        showToast("Sign in first.", true);
        return;
    }
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
        await Promise.allSettled([loadDeveloperSkills(), loadSkills(), loadFeaturedSkills()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleUploadVersion(event) {
    event.preventDefault();
    if (!state.token) {
        showToast("Sign in first.", true);
        return;
    }
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
        await Promise.allSettled([loadDeveloperSkills(), loadReviews(), loadAdminStats()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleReviewAction(reviewId, action) {
    if (!state.token || state.user?.role !== "store_admin") {
        showToast("Store admin access required.", true);
        return;
    }
    const comment = window.prompt(`Optional comment for ${action}:`, "");
    if (comment === null) {
        return;
    }
    try {
        await apiFetch(`/api/v1/admin/reviews/${reviewId}/${action}`, {
            method: "POST",
            body: JSON.stringify({ comment }),
        });
        showToast(`Review ${action}d.`);
        await Promise.allSettled([loadReviews(), loadAdminStats(), loadSkills(), loadFeaturedSkills()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function handleRevoke(event) {
    event.preventDefault();
    if (!state.token || state.user?.role !== "store_admin") {
        showToast("Store admin access required.", true);
        return;
    }
    try {
        const formData = new FormData(event.currentTarget);
        const certificateSerial = formData.get("certificate_serial");
        await apiFetch(`/api/v1/admin/certifications/${encodeURIComponent(certificateSerial)}/revoke`, {
            method: "POST",
            body: JSON.stringify({ comment: formData.get("comment") }),
        });
        showToast("Certificate revoked.");
        event.currentTarget.reset();
        await Promise.allSettled([loadReviews(), loadAdminStats()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

function logout(showMessage) {
    state.token = "";
    state.user = null;
    localStorage.removeItem("skillsStoreToken");
    localStorage.removeItem("skillsStoreUser");
    renderCurrentUser();
    setButtonsState();
    renderDeveloperSkills([]);
    renderReviews();
    renderAdminStats();
    if (showMessage) {
        showToast("Signed out.");
    }
}

function renderCategories() {
    const categoryOptions = ['<option value="">All categories</option>']
        .concat(state.categories.map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`))
        .join("");
    const developerOptions = ['<option value="">Choose category</option>']
        .concat(state.categories.map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`))
        .join("");
    els.categorySelect.innerHTML = categoryOptions;
    els.developerCategorySelect.innerHTML = developerOptions;
}

function renderSkills() {
    const term = els.searchInput.value.trim().toLowerCase();
    const category = els.categorySelect.value;
    const filtered = state.skills.filter((item) => {
        const matchesCategory = !category || item.category === category;
        const haystack = [item.name, item.display_name, item.summary].join(" ").toLowerCase();
        const matchesSearch = !term || haystack.includes(term);
        return matchesCategory && matchesSearch;
    });
    els.skillsMeta.textContent = `${filtered.length} items`;
    els.statsSkills.textContent = String(filtered.length);
    if (!filtered.length) {
        els.skillsList.innerHTML = '<div class="console-empty">No skills match the current filter.</div>';
        return;
    }
    els.skillsList.innerHTML = filtered.map(renderSkillCard).join("");
    bindSkillCardActions();
}

function renderFeaturedSkills() {
    els.featuredMeta.textContent = `${state.featured.length} items`;
    els.statsFeatured.textContent = String(state.featured.length);
    if (!state.featured.length) {
        els.featuredSkills.innerHTML = '<div class="console-empty">No featured skills available.</div>';
        return;
    }
    els.featuredSkills.innerHTML = state.featured.map(renderSkillCard).join("");
    bindSkillCardActions();
}

function renderSkillCard(skill) {
    return `
        <article class="console-card skill-card-live">
            <div class="console-card-head">
                <div>
                    <h4>${escapeHtml(skill.display_name || skill.name)}</h4>
                    <p class="console-muted">${escapeHtml(skill.name)}</p>
                </div>
                <span class="console-tag">${escapeHtml(skill.category || "unknown")}</span>
            </div>
            <p>${escapeHtml(skill.summary || "No summary provided.")}</p>
            <div class="console-card-meta">
                <span>Status: ${escapeHtml(skill.status || "unknown")}</span>
                <span>Version: ${escapeHtml(skill.latest_version || "-")}</span>
                <span>Downloads: ${escapeHtml(String(skill.download_count || 0))}</span>
            </div>
            <div class="console-card-actions">
                <button class="btn btn-secondary btn-sm skill-detail-btn" data-skill-name="${escapeHtml(skill.name)}">Details</button>
            </div>
        </article>
    `;
}

function bindSkillCardActions() {
    document.querySelectorAll(".skill-detail-btn").forEach((button) => {
        button.addEventListener("click", async () => {
            await openSkillDetail(button.dataset.skillName);
        });
    });
}

async function openSkillDetail(skillName) {
    try {
        const skill = await apiFetch(`/api/v1/skills/${encodeURIComponent(skillName)}`);
        const versions = await apiFetch(`/api/v1/skills/${encodeURIComponent(skillName)}/versions`);
        els.modalBody.innerHTML = `
            <div class="console-modal-head">
                <div>
                    <h2>${escapeHtml(skill.display_name || skill.name)}</h2>
                    <p class="console-muted">${escapeHtml(skill.name)} · ${escapeHtml(skill.category || "unknown")}</p>
                </div>
                <span class="console-tag">${escapeHtml(skill.status || "unknown")}</span>
            </div>
            <p>${escapeHtml(skill.description || skill.summary || "No description available.")}</p>
            <h3 class="console-subtitle">Versions</h3>
            <div class="console-card-list">
                ${versions.length ? versions.map((version) => `
                    <div class="console-card compact">
                        <div class="console-card-head">
                            <strong>${escapeHtml(version.version)}</strong>
                            <span class="console-tag">${escapeHtml(version.status)}</span>
                        </div>
                        <p>Hash: ${escapeHtml(version.package_hash)}</p>
                        <p>Package size: ${escapeHtml(String(version.package_size))} bytes</p>
                    </div>
                `).join("") : '<div class="console-empty">No versions found.</div>'}
            </div>
        `;
        els.modal.classList.add("active");
        document.body.style.overflow = "hidden";
    } catch (error) {
        showToast(error.message, true);
    }
}

function closeModal() {
    els.modal.classList.remove("active");
    document.body.style.overflow = "";
}

function renderCurrentUser() {
    if (!state.user) {
        els.userRole.textContent = "Guest";
        els.currentUserCard.innerHTML = "<p>No active session.</p>";
        els.profileForm.reset();
        return;
    }
    els.userRole.textContent = state.user.role;
    els.currentUserCard.innerHTML = `
        <h4>${escapeHtml(state.user.name)}</h4>
        <p>${escapeHtml(state.user.email)}</p>
        <p>Role: ${escapeHtml(state.user.role)}</p>
        <p>Status: ${escapeHtml(state.user.status)}</p>
    `;
    els.profileForm.elements.name.value = state.user.name || "";
    els.profileForm.elements.bio.value = state.user.bio || "";
    els.profileForm.elements.website.value = state.user.website || "";
}

function renderDeveloperSkills(skills) {
    els.developerSkillsMeta.textContent = state.token ? `${skills.length} records` : "Login required";
    if (!skills.length) {
        els.developerSkillsBody.innerHTML = '<tr><td colspan="5">No skills yet.</td></tr>';
        return;
    }
    els.developerSkillsBody.innerHTML = skills.map((skill) => `
        <tr>
            <td>${escapeHtml(skill.name)}</td>
            <td>${escapeHtml(skill.category || "-")}</td>
            <td>${escapeHtml(skill.latest_version || "-")}</td>
            <td>${escapeHtml(skill.status || "-")}</td>
            <td>${escapeHtml(String(skill.download_count || 0))}</td>
        </tr>
    `).join("");
}

function renderReviews() {
    const pending = state.reviews.filter((item) => item.status === "pending").length;
    els.statsReviews.textContent = String(pending);
    els.reviewsMeta.textContent = `${state.reviews.length} records`;
    if (!state.token || state.user?.role !== "store_admin") {
        els.reviewsList.innerHTML = '<div class="console-empty">Store admin login required.</div>';
        return;
    }
    if (!state.reviews.length) {
        els.reviewsList.innerHTML = '<div class="console-empty">No review items found.</div>';
        return;
    }
    els.reviewsList.innerHTML = state.reviews.map((review) => `
        <article class="console-card review-card">
            <div class="console-card-head">
                <div>
                    <h4>${escapeHtml(review.display_name || review.skill_name)}</h4>
                    <p class="console-muted">${escapeHtml(review.skill_name)} · ${escapeHtml(review.version)}</p>
                </div>
                <span class="console-tag">${escapeHtml(review.status)}</span>
            </div>
            <p>Developer: ${escapeHtml((review.developer && review.developer.name) || "Unknown")}</p>
            <p>Scan status: ${escapeHtml((review.scan_summary && review.scan_summary.status) || "pending")}</p>
            <p>Version status: ${escapeHtml(review.version_status || "reviewing")}</p>
            <div class="console-card-actions">
                <button class="btn btn-outline btn-sm" onclick="handleReviewAction(${review.id}, 'start')">Start</button>
                <button class="btn btn-primary btn-sm" onclick="handleReviewAction(${review.id}, 'approve')">Approve</button>
                <button class="btn btn-secondary btn-sm" onclick="handleReviewAction(${review.id}, 'reject')">Reject</button>
            </div>
        </article>
    `).join("");
}

function renderAdminStats() {
    if (!state.token || state.user?.role !== "store_admin") {
        els.adminStats.innerHTML = '<div class="console-empty">Store admin login required.</div>';
        return;
    }
    if (!state.adminStats) {
        els.adminStats.innerHTML = '<div class="console-empty">No stats available yet.</div>';
        return;
    }
    els.adminStats.innerHTML = Object.entries(state.adminStats).map(([key, value]) => `
        <div class="console-metric">
            <span class="console-metric-label">${escapeHtml(key.replaceAll("_", " "))}</span>
            <strong class="console-metric-value">${escapeHtml(String(value))}</strong>
        </div>
    `).join("");
}

function setButtonsState() {
    els.logoutBtn.disabled = !state.token;
}

function setApiStatus(mode, message) {
    const labels = {
        idle: "Endpoint not tested",
        pending: "Checking...",
        ok: "Connected",
        error: "Connection failed",
    };
    els.apiStatusPill.textContent = labels[mode] || mode;
    els.apiStatusPill.className = `console-status-pill ${mode}`;
    els.apiStatusText.textContent = message;
}

function showToast(message, isError) {
    els.toast.textContent = message;
    els.toast.className = `console-toast show${isError ? " error" : ""}`;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
        els.toast.className = "console-toast";
    }, 2600);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

window.handleReviewAction = handleReviewAction;

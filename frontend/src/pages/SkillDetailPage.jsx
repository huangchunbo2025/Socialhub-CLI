import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Layout from "../components/Layout";
import { apiFetch, loadSavedSkills, saveSavedSkills } from "../lib/api";
import { getSavedSkillNames } from "../lib/session";
import { useToast } from "../components/ToastProvider";

function renderListSection(section) {
  return (
    <article key={section.title} className="detail-card">
      <h3>{section.title}</h3>
      {section.body ? <p>{section.body}</p> : null}
      {Array.isArray(section.items) ? (
        <ul>
          {section.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      {section.command ? <code className="command-block">{section.command}</code> : null}
    </article>
  );
}

export default function SkillDetailPage() {
  const { name } = useParams();
  const [skill, setSkill] = useState(null);
  const [versions, setVersions] = useState([]);
  const [savedSkills, setSavedSkills] = useState(getSavedSkillNames());
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const [detail, versionList] = await Promise.all([
          apiFetch(`/api/v1/skills/${encodeURIComponent(name)}`),
          apiFetch(`/api/v1/skills/${encodeURIComponent(name)}/versions`)
        ]);
        const storedSaved = await loadSavedSkills();
        if (cancelled) return;
        setSkill(detail);
        setVersions(versionList || []);
        setSavedSkills(storedSaved);
      } catch (loadError) {
        if (!cancelled) setError(loadError.message || "Failed to load skill detail.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [name]);

  async function handleToggleSaved(skillName) {
    const current = new Set(savedSkills);
    if (current.has(skillName)) {
      current.delete(skillName);
    } else {
      current.add(skillName);
    }
    const persisted = await saveSavedSkills([...current]);
    setSavedSkills(persisted);
    const nowSaved = persisted.includes(skillName);
    toast.show(nowSaved ? "Added to My skills." : "Removed from My skills.");
  }

  return (
    <Layout
      title={skill?.display_name || "Skill detail"}
      subtitle={skill?.summary || "Review trust signals, runtime requirements, and CLI install guidance."}
      actions={
        skill ? (
          <aside className="side-note">
            <h2>Install from CLI</h2>
            <code className="command-block">socialhub skills install {skill.name}</code>
              <button
                className="outline-button wide"
                type="button"
                onClick={() => handleToggleSaved(skill.name)}
              >
                {savedSkills.includes(skill.name) ? "Saved to My skills" : "Add to My skills"}
              </button>
            </aside>
          ) : null
      }
    >
      {loading ? <section className="panel">Loading skill detail...</section> : null}
      {error ? <section className="panel error">{error}</section> : null}

      {skill ? (
        <>
          <section className="detail-grid">
            <article className="detail-card">
              <h3>Release snapshot</h3>
              <dl className="detail-list">
                <div>
                  <dt>Publisher</dt>
                  <dd>{skill.developer?.name || "Unknown"}</dd>
                </div>
                <div>
                  <dt>Latest version</dt>
                  <dd>{skill.latest_version || "N/A"}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{skill.status}</dd>
                </div>
                <div>
                  <dt>Downloads</dt>
                  <dd>{skill.download_count || 0}</dd>
                </div>
                <div>
                  <dt>License</dt>
                  <dd>{skill.license_name || "Not declared"}</dd>
                </div>
              </dl>
            </article>
            <article className="detail-card">
              <h3>Overview</h3>
              <p>{skill.description}</p>
              <div className="tag-row">
                {(skill.tags || []).map((tag) => (
                  <span key={tag} className="tag">
                    {tag}
                  </span>
                ))}
              </div>
            </article>
          </section>

          <section className="detail-stack">
            {(skill.security_review || []).map(renderListSection)}
            {(skill.runtime_requirements || []).map(renderListSection)}
            {(skill.install_guidance || []).map(renderListSection)}
            {(skill.docs_sections || []).map(renderListSection)}
          </section>

          <section className="detail-card">
            <div className="section-header">
              <h3>Versions</h3>
              <Link className="secondary-link" to="/user">
                Go to My skills
              </Link>
            </div>
            <div className="version-list">
              {versions.map((version) => (
                <article key={version.id} className="version-card">
                  <strong>{version.version}</strong>
                  <p>{version.release_notes || "No release notes provided."}</p>
                  <code className="command-block">socialhub skills install {skill.name}@{version.version}</code>
                </article>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </Layout>
  );
}

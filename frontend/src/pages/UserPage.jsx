import { useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import Layout from "../components/Layout";
import { apiFetch, loadCurrentUser, loadSavedSkills, saveSavedSkills } from "../lib/api";
import { getSavedSkillNames, getSkillEnabledState, getStoredUser, toggleSkillEnabledState } from "../lib/session";
import { useToast } from "../components/ToastProvider";

export default function UserPage() {
  const [skills, setSkills] = useState([]);
  const [user, setUser] = useState(getStoredUser());
  const [savedSkills, setSavedSkills] = useState(getSavedSkillNames());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const currentUser = await loadCurrentUser();
        if (cancelled) return;
        setUser(currentUser);
        if (!currentUser) {
          setLoading(false);
          return;
        }
        const catalog = await apiFetch("/api/v1/skills");
        const storedSaved = await loadSavedSkills();
        if (cancelled) return;
        setSkills(catalog.data || catalog || []);
        setSavedSkills(storedSaved);
      } catch (loadError) {
        if (!cancelled) setError(loadError.message || "Failed to load My skills.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [version]);

  const mySkills = useMemo(() => {
    const saved = new Set(savedSkills);
    return skills.filter((skill) => saved.has(skill.name));
  }, [skills, savedSkills, version]);

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
    return nowSaved;
  }

  if (!loading && !user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <Layout
      title="My skills"
      subtitle="Track the skills you want to keep close, switch them on or off locally, and return to the catalog when you need more."
    >
      {user ? (
        <section className="panel workspace-summary">
          <div>
            <p className="eyebrow">Signed in as</p>
            <h2>{user.name || user.email}</h2>
            <p>{user.email}</p>
          </div>
          <div className="workspace-summary-stats">
            <div>
              <strong>{mySkills.length}</strong>
              <span>Saved skills</span>
            </div>
            <div>
              <strong>{mySkills.filter((skill) => getSkillEnabledState(skill.name)).length}</strong>
              <span>Enabled now</span>
            </div>
          </div>
        </section>
      ) : null}
      {loading ? <section className="panel">Loading your workspace...</section> : null}
      {error ? <section className="panel error">{error}</section> : null}

      {!loading && !error ? (
        <section className="panel">
          <div className="section-header">
            <h2>Saved skills</h2>
            <p>{mySkills.length} skills in your personal working set</p>
          </div>
          {mySkills.length === 0 ? (
            <div className="empty-state">
              <p>No skills saved yet. Start from the catalog and add the skills you want to keep close.</p>
              <Link className="secondary-link" to="/">
                Back to store
              </Link>
            </div>
          ) : (
            <div className="workspace-list">
              {mySkills.map((skill) => {
                const enabled = getSkillEnabledState(skill.name);
                return (
                  <article key={skill.id} className="workspace-card">
                    <div>
                      <h3>{skill.display_name}</h3>
                      <p>{skill.summary}</p>
                    </div>
                    <div className="workspace-actions">
                      <button
                        className={enabled ? "state-button enabled" : "state-button disabled"}
                        type="button"
                        onClick={() => {
                          const next = toggleSkillEnabledState(skill.name);
                          setVersion((value) => value + 1);
                          toast.show(next ? "Skill enabled." : "Skill disabled.");
                        }}
                      >
                        {enabled ? "Enabled" : "Disabled"}
                      </button>
                      <button
                        className="outline-button"
                        type="button"
                        onClick={() => handleToggleSaved(skill.name)}
                      >
                        Remove from My skills
                      </button>
                      <Link className="secondary-link" to={`/skill/${encodeURIComponent(skill.name)}`}>
                        View detail
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      ) : null}
    </Layout>
  );
}

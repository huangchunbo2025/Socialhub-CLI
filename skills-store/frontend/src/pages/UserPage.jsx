import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import Layout from "../components/Layout";
import { loadCurrentStorefrontUser, loadMyUserSkills, removeUserSkill, toggleUserSkill } from "../lib/api";
import { getStoredStorefrontUser } from "../lib/session";
import { useToast } from "../components/ToastProvider";

export default function UserPage() {
  const [skills, setSkills] = useState([]);
  const [user, setUser] = useState(getStoredStorefrontUser());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const currentUser = await loadCurrentStorefrontUser();
        if (cancelled) return;
        setUser(currentUser);
        if (!currentUser) {
          setLoading(false);
          return;
        }
        const library = await loadMyUserSkills();
        if (cancelled) return;
        setSkills(library || []);
      } catch (loadError) {
        if (!cancelled) setError(loadError.message || "Failed to load My Skills.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!loading && !user) {
    return <Navigate to="/user-login" replace />;
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
              <strong>{skills.length}</strong>
              <span>Installed skills</span>
            </div>
            <div>
              <strong>{skills.filter((skill) => skill.is_enabled).length}</strong>
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
            <h2>My Skills</h2>
            <p>{skills.length} skills in your shared storefront library</p>
          </div>
          {skills.length === 0 ? (
            <div className="empty-state">
              <p>Your library is empty. Browse the store to install skills.</p>
              <Link className="secondary-link" to="/">
                Browse catalog
              </Link>
            </div>
          ) : (
            <div className="workspace-list">
              {skills.map((skill) => {
                return (
                  <article key={`${skill.skill_name}-${skill.version}`} className="workspace-card">
                    <div>
                      <h3>{skill.display_name}</h3>
                      <p>{skill.description}</p>
                      <p className="workspace-meta">{skill.version} · {skill.category}</p>
                    </div>
                    <div className="workspace-actions">
                      <button
                        className={skill.is_enabled ? "state-button enabled" : "state-button disabled"}
                        type="button"
                        onClick={async () => {
                          try {
                            const updated = await toggleUserSkill(skill.skill_name, !skill.is_enabled);
                            setSkills((current) =>
                              current.map((item) => (item.skill_name === skill.skill_name ? updated : item))
                            );
                            toast.show(updated.is_enabled ? "Skill enabled." : "Skill disabled.");
                          } catch (toggleError) {
                            toast.show(toggleError.message || "Failed to change skill state.");
                          }
                        }}
                      >
                        {skill.is_enabled ? "Enabled" : "Disabled"}
                      </button>
                      <button
                        className="outline-button"
                        type="button"
                        onClick={async () => {
                          try {
                            await removeUserSkill(skill.skill_name);
                            setSkills((current) => current.filter((item) => item.skill_name !== skill.skill_name));
                            toast.show("Removed from your library.");
                          } catch (removeError) {
                            toast.show(removeError.message || "Failed to remove skill.");
                          }
                        }}
                      >
                        Remove
                      </button>
                      <Link className="secondary-link" to={`/skill/${encodeURIComponent(skill.skill_name)}`}>
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

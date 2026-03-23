import { useEffect, useMemo, useState } from "react";
import Layout from "../components/Layout";
import SkillCard from "../components/SkillCard";
import { apiFetch, loadSavedSkills, saveSavedSkills } from "../lib/api";
import { CATEGORY_META } from "../lib/categoryMeta";
import { getSavedSkillNames } from "../lib/session";

export default function CatalogPage() {
  const [skills, setSkills] = useState([]);
  const [categories, setCategories] = useState([]);
  const [savedSkills, setSavedSkills] = useState(getSavedSkillNames());
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const [catalog, categoryList] = await Promise.all([
          apiFetch("/api/v1/skills"),
          apiFetch("/api/v1/categories")
        ]);
        const storedSaved = await loadSavedSkills();
        if (cancelled) return;
        setSkills(catalog.data || catalog || []);
        setCategories(categoryList || []);
        setSavedSkills(storedSaved);
      } catch (loadError) {
        if (!cancelled) setError(loadError.message || "Failed to load catalog.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    return skills.filter((skill) => {
      const matchesCategory = activeCategory === "all" || skill.category === activeCategory;
      const haystack = `${skill.display_name} ${skill.summary} ${skill.description || ""}`.toLowerCase();
      const matchesQuery = haystack.includes(query.toLowerCase());
      return matchesCategory && matchesQuery;
    });
  }, [skills, activeCategory, query]);

  async function handleToggleSaved(skillName) {
    const current = new Set(savedSkills);
    if (current.has(skillName)) {
      current.delete(skillName);
    } else {
      current.add(skillName);
    }
    const persisted = await saveSavedSkills([...current]);
    setSavedSkills(persisted);
    return persisted.includes(skillName);
  }

  return (
    <Layout
      title="Reviewed skills for real operators"
      subtitle="Search the live catalog, inspect detail pages, and install approved skills through the SocialHub CLI."
      actions={
        <aside className="hero-sidecard">
          <h2>Before you install</h2>
          <p>Evaluate a skill the same way an operations team would before it reaches production.</p>
          <div className="hero-sidecard-list">
            <div>
              <strong>Review the publisher</strong>
              <span>Confirm who maintains the skill and whether the publishing history looks stable and accountable.</span>
            </div>
            <div>
              <strong>Inspect the release</strong>
              <span>Check runtime requirements, security notes, and current version metadata.</span>
            </div>
            <div>
              <strong>Install from the CLI</strong>
              <span>Copy the install command only after the skill passes your rollout criteria.</span>
            </div>
          </div>
        </aside>
      }
    >
      <section className="toolbar">
        <input
          className="search-input"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by skill name, summary, or workflow"
        />
        <p className="result-count">{filtered.length} skills visible</p>
      </section>

      <section className="category-tabs">
        <button
          className={activeCategory === "all" ? "category-chip active" : "category-chip"}
          type="button"
          onClick={() => setActiveCategory("all")}
        >
          <span dangerouslySetInnerHTML={{ __html: CATEGORY_META.all.svg }} />
          <span>All</span>
        </button>
        {categories.map((category) => (
          <button
            key={category.key}
            className={activeCategory === category.key ? "category-chip active" : "category-chip"}
            type="button"
            onClick={() => setActiveCategory(category.key)}
          >
            <span
              dangerouslySetInnerHTML={{
                __html: (CATEGORY_META[category.key] || CATEGORY_META.all).svg
              }}
            />
            <span>{category.label}</span>
          </button>
        ))}
      </section>

      {loading ? <section className="panel">Loading catalog...</section> : null}
      {error ? <section className="panel error">{error}</section> : null}

      {!loading && !error ? (
        <section className="catalog-grid">
          {filtered.map((skill) => (
            <SkillCard
              key={skill.id}
              skill={skill}
              saved={savedSkills.includes(skill.name)}
              onToggleSaved={handleToggleSaved}
            />
          ))}
        </section>
      ) : null}
    </Layout>
  );
}

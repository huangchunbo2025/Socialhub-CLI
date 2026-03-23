import { Link } from "react-router-dom";
import { useToast } from "./ToastProvider";
import { CATEGORY_META } from "../lib/categoryMeta";

export default function SkillCard({ skill, saved, onToggleSaved }) {
  const toast = useToast();
  const categoryMeta = CATEGORY_META[skill.category] || CATEGORY_META.all;

  return (
    <article className="skill-card">
      <div className="skill-card-top">
        <span className="status-pill">{saved ? "Saved" : categoryMeta.label}</span>
        <span className="skill-downloads">{skill.download_count ?? 0} downloads</span>
      </div>
      <div className="skill-card-headline">
        <div
          className={`skill-icon ${categoryMeta.className}`}
          dangerouslySetInnerHTML={{ __html: categoryMeta.svg }}
        />
        <div className="skill-card-title">
          <h3>{skill.display_name}</h3>
          <p className="skill-card-slug">{skill.name}</p>
        </div>
      </div>
      <p className="skill-summary">{skill.summary}</p>
      <dl className="skill-meta">
        <div>
          <dt>Latest</dt>
          <dd>{skill.latest_version || "N/A"}</dd>
        </div>
        <div>
          <dt>Downloads</dt>
          <dd>{skill.download_count ?? 0}</dd>
        </div>
      </dl>
      <div className="skill-card-actions">
        <Link className="secondary-link" to={`/skill/${encodeURIComponent(skill.name)}`}>
          View detail
        </Link>
        <button
          className="outline-button"
          type="button"
          onClick={async () => {
            const nextSaved = await onToggleSaved?.(skill.name);
            toast.show(nextSaved ? "Added to My skills." : "Removed from My skills.");
          }}
        >
          {saved ? "Saved" : "Add to My skills"}
        </button>
      </div>
    </article>
  );
}

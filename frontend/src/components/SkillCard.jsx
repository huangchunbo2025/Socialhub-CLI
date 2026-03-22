import { Link } from "react-router-dom";
import { useToast } from "./ToastProvider";

export default function SkillCard({ skill, saved, onToggleSaved }) {
  const toast = useToast();

  return (
    <article className="skill-card">
      <div className="skill-card-header">
        <div>
          <h3>{skill.display_name}</h3>
          <p>{skill.summary}</p>
        </div>
        <span className={`status-pill status-${skill.status}`}>{saved ? "Saved" : skill.category}</span>
      </div>
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

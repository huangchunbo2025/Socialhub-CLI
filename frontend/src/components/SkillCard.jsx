import { Link } from "react-router-dom";
import { CATEGORY_META } from "../lib/categoryMeta";

export default function SkillCard({ skill, installed, isSignedIn }) {
  const categoryMeta = CATEGORY_META[skill.category] || CATEGORY_META.all;

  return (
    <article className="skill-card">
      <div className="skill-card-top">
        <span className="status-pill">{installed ? "Installed" : categoryMeta.label}</span>
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
        <Link className="outline-button button-link" to={isSignedIn ? `/skill/${encodeURIComponent(skill.name)}` : "/user-login"}>
          {!isSignedIn ? "Login to Install" : installed ? "Installed" : "Install"}
        </Link>
      </div>
    </article>
  );
}

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { loadCurrentUser, loginUser } from "../lib/api";

export default function LoginPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function checkSession() {
      const user = await loadCurrentUser();
      if (active && user) {
        navigate("/user", { replace: true });
      }
    }
    checkSession();
    return () => {
      active = false;
    };
  }, [navigate]);

  async function handleSubmit(event) {
    event.preventDefault();
    try {
      setSubmitting(true);
      setError("");
      await loginUser(form);
      navigate("/user", { replace: true });
    } catch (submitError) {
      setError(submitError.message || "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Layout
      title="Sign in to continue from the storefront"
      subtitle="Keep the flow simple: review a skill, confirm the release, then return to your workspace ready to install through the CLI."
      actions={
        <aside className="side-note">
          <h2>What changes after sign-in</h2>
          <ul>
            <li>Keep a personal list of skills you want to track.</li>
            <li>Switch saved skills on or off in your workspace.</li>
            <li>Return to the catalog without losing your shortlist.</li>
          </ul>
        </aside>
      }
    >
      <section className="auth-layout">
        <article className="panel auth-panel-copy">
          <p className="eyebrow">Store entry</p>
          <h2>Review first. Install from the CLI after approval.</h2>
          <p>
            The store is built for evaluation. Read the detail page, confirm the current release,
            and then copy the install command into SocialHub CLI.
          </p>
          <div className="auth-points">
            <div>
              <strong>1</strong>
              <span>Inspect trust and runtime requirements</span>
            </div>
            <div>
              <strong>2</strong>
              <span>Save the skills you want to keep close</span>
            </div>
            <div>
              <strong>3</strong>
              <span>Install only through the CLI workflow</span>
            </div>
          </div>
        </article>

        <article className="panel auth-form-card">
          <h2>Store sign in</h2>
          <form className="auth-form" onSubmit={handleSubmit}>
            <label>
              Email
              <input
                type="email"
                value={form.email}
                onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={form.password}
                onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                required
                minLength={8}
              />
            </label>
            {error ? <p className="error-copy">{error}</p> : null}
            <button className="cli-button wide" type="submit" disabled={submitting}>
              {submitting ? "Signing in..." : "Continue to My skills"}
            </button>
          </form>
          <Link className="secondary-link auth-back-link" to="/">
            Back to store
          </Link>
        </article>
      </section>
    </Layout>
  );
}

import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { loadCurrentStorefrontUser, loginStorefrontUser } from "../lib/api";

export default function UserLoginPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function checkSession() {
      const user = await loadCurrentStorefrontUser();
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
      await loginStorefrontUser(form);
      navigate("/user", { replace: true });
    } catch (submitError) {
      setError(submitError.message || "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Layout
      title="Sign in to manage your skill library"
      subtitle="Your web library is shared with the CLI catalog flow. Install in the browser adds a skill to your library; actual package download still happens in the CLI."
      actions={
        <aside className="hero-sidecard">
          <h2>What changes after sign-in</h2>
          <p>Storefront users get a personal library that stays in sync with authenticated CLI skill management.</p>
          <div className="hero-sidecard-list">
            <div>
              <strong>Install to library</strong>
              <span>Add a reviewed skill to your personal library from the detail page.</span>
            </div>
            <div>
              <strong>Control enabled state</strong>
              <span>Turn a skill on or off from your web library and let the CLI reflect that state.</span>
            </div>
            <div>
              <strong>Keep CLI execution separate</strong>
              <span>Run `socialhub skills install &lt;name&gt;` only when you want the package on your machine.</span>
            </div>
          </div>
        </aside>
      }
    >
      <section className="auth-layout">
        <article className="panel auth-panel-copy">
          <p className="eyebrow">Storefront user</p>
          <h2>Build your working library first.</h2>
          <p>
            Review skill detail pages, add approved skills to your library, and keep your CLI workflow aligned with the same inventory.
          </p>
          <div className="auth-points">
            <div>
              <strong>1</strong>
              <span>Inspect trust and runtime requirements</span>
            </div>
            <div>
              <strong>2</strong>
              <span>Add the right skills to your shared library</span>
            </div>
            <div>
              <strong>3</strong>
              <span>Install locally only when you are ready</span>
            </div>
          </div>
        </article>

        <article className="panel auth-form-card">
          <h2>User sign in</h2>
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
          <p className="auth-switch-copy">
            Working as a publisher or reviewer? <Link to="/login">Go to developer/admin sign-in.</Link>
          </p>
        </article>
      </section>
    </Layout>
  );
}

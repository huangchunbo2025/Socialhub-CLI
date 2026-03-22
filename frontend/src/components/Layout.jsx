import { Link } from "react-router-dom";
import { clearSession, getStoredUser } from "../lib/session";

function Footer() {
  return (
    <footer className="site-footer">
      <div>
        <strong>SocialHub Skills Store</strong>
        <p>Evaluate reviewed skills, inspect release details, and install from the SocialHub CLI.</p>
      </div>
      <div className="footer-links">
        <a href="https://skills-store-backend.onrender.com/openapi.json" target="_blank" rel="noreferrer">
          API schema
        </a>
        <a href="https://skills-store-backend.onrender.com/health" target="_blank" rel="noreferrer">
          Backend health
        </a>
        <a href="#/login">Store sign in</a>
      </div>
    </footer>
  );
}

export default function Layout({ title, subtitle, actions, children }) {
  const user = getStoredUser();

  return (
    <div className="app-shell">
      <header className="site-header">
        <Link className="brand" to="/">
          <span className="brand-mark">S</span>
          <span>SocialHub Skills Store</span>
        </Link>
        <div className="header-actions">
          <button
            className="cli-button"
            type="button"
            onClick={() => window.alert("Use `socialhub skills install <skill-name>` in the CLI.")}
          >
            &gt;_ CLI Install
          </button>
          {user ? (
            <>
              <Link className="auth-link" to="/user">
                My skills
              </Link>
              <button
                className="outline-button"
                type="button"
                onClick={() => {
                  clearSession();
                  window.location.hash = "#/";
                }}
              >
                Sign out
              </button>
            </>
          ) : (
            <Link className="auth-link" to="/login">
              Sign in
            </Link>
          )}
        </div>
      </header>

      <main className="page-shell">
        <section className="page-hero">
          <div>
            <p className="eyebrow">Storefront</p>
            <h1>{title}</h1>
            {subtitle ? <p className="hero-copy">{subtitle}</p> : null}
          </div>
          {actions ? <div className="hero-actions">{actions}</div> : null}
        </section>
        {children}
      </main>

      <Footer />
    </div>
  );
}

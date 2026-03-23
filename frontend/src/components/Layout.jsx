import { Link } from "react-router-dom";
import { clearSession, getStoredUser } from "../lib/session";

function Footer() {
  return (
    <footer className="footer">
      <div className="container footer-content-wrap">
        <div className="footer-content">
          <div className="footer-brand">
            <img src={`${import.meta.env.BASE_URL}logo.png`} alt="SocialHub.AI" className="logo-img-footer" />
            <p className="footer-tagline">
              A storefront for trusted discovery, with a formal React preview for the next production storefront.
            </p>
          </div>
          <div className="footer-links">
            <div className="footer-column">
              <h4>Store</h4>
              <a href="#/">Catalog</a>
              <a href="#/skill/sales-daily-brief">Example skill</a>
            </div>
            <div className="footer-column">
              <h4>Access</h4>
              <a href="#/login">Store sign in</a>
              <a href="https://skills-store-backend.onrender.com/openapi.json" target="_blank" rel="noreferrer">
                API schema
              </a>
              <a href="https://skills-store-backend.onrender.com/health" target="_blank" rel="noreferrer">
                Backend health
              </a>
            </div>
          </div>
        </div>
        <div className="footer-bottom">
          <p className="copyright">&copy; 2026 SocialHub.AI. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}

export default function Layout({ title, subtitle, actions, children }) {
  const user = getStoredUser();

  return (
    <div className="app-shell">
      <nav className="navbar">
        <div className="nav-container">
          <Link className="nav-logo" to="/">
            <img src={`${import.meta.env.BASE_URL}logo.png`} alt="SocialHub.AI" className="logo-img" />
            <span className="nav-divider">|</span>
            <span className="nav-subtitle">Skills Store</span>
          </Link>
          <div className="nav-actions">
            <button
              className="btn btn-cli"
              type="button"
              onClick={() => window.alert("Use `socialhub skills install <skill-name>` in the CLI.")}
            >
              &gt;_ CLI Install
            </button>
            {user ? (
              <>
                <Link className="btn btn-primary" to="/user">
                  My skills
                </Link>
                <button
                  className="btn btn-outline"
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
              <Link className="btn btn-primary" to="/login">
                Sign in
              </Link>
            )}
          </div>
        </div>
      </nav>

      <main className="page-shell">
        <section className="hero product-hero">
          <div className="hero-bg"></div>
          <div className="container">
            <div className="product-hero-grid">
              <div className="product-copy">
                <div className="hero-badge">
                  <span className="badge-icon">Live</span>
                  React storefront preview
                </div>
                <h1 className="hero-title">{title}</h1>
                {subtitle ? <p className="hero-subtitle">{subtitle}</p> : null}
              </div>
              {actions ? <div>{actions}</div> : null}
            </div>
          </div>
        </section>
        <div className="container page-content">{children}</div>
      </main>

      <Footer />
    </div>
  );
}

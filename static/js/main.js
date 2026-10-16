// ── NAVBAR scroll effect ─────────────────────────────────────
window.addEventListener('scroll', () => {
  const nav = document.querySelector('.navbar');
  if (nav) nav.classList.toggle('scrolled', window.scrollY > 40);
});

// ── ACTIVE nav link ──────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const page = window.location.pathname;
  document.querySelectorAll('.nav-links a').forEach(a => {
    if (a.getAttribute('href') === page) a.classList.add('active');
  });
});

// ── SMOOTH fade-up on scroll ─────────────────────────────────
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.15 });

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.scroll-reveal').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(30px)';
    el.style.transition = 'opacity 0.7s ease, transform 0.7s ease';
    observer.observe(el);
  });
});

// ── NAVBAR HTML injector (call on each page) ─────────────────
function injectNav() {
  const nav = document.querySelector('#navbar-placeholder');
  if (!nav) return;
  nav.innerHTML = `
    <nav class="navbar">
      <a href="/" class="nav-logo">
        <div class="nav-logo-dot">&#9825;</div>
        MindSpace
      </a>
      <ul class="nav-links">
        <li><a href="/">Home</a></li>
        <li><a href="/about/">About</a></li>
        <li><a href="/contact/">Contact</a></li>
      </ul>
      <div class="nav-cta">
        <a href="/help/" class="btn btn-terra btn-help-now">Get help now</a>
        <a href="/accounts/login/" class="btn btn-outline">Log in</a>
        <a href="/accounts/signup/" class="btn btn-primary">Get started</a>
      </div>
    </nav>`;
}

// ── FOOTER HTML injector ─────────────────────────────────────
function injectFooter() {
  const f = document.querySelector('#footer-placeholder');
  if (!f) return;
  f.innerHTML = `
    <footer>
      <div class="footer-inner">
        <div class="footer-brand">
          <div class="nav-logo">
            <div class="nav-logo-dot">&#9825;</div>
            MindSpace
          </div>
          <p>A safe, compassionate space for your mental wellness journey. Available whenever you need support.</p>
        </div>
        <div class="footer-col">
          <h4>Product</h4>
          <ul>
            <li><a href="#">Features</a></li>
            <li><a href="#">Pricing</a></li>
            <li><a href="#">Download</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h4>Company</h4>
          <ul>
            <li><a href="/about/">About</a></li>
            <li><a href="/contact/">Contact</a></li>
            <li><a href="#">Blog</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h4>Support</h4>
          <ul>
            <li><a href="#">Help Centre</a></li>
            <li><a href="#">Privacy Policy</a></li>
            <li><a href="#">Terms of Use</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; 2025 MindSpace. All rights reserved.</span>
        <span>Not a substitute for professional mental health care.</span>
      </div>
    </footer>`;
}

document.addEventListener('DOMContentLoaded', () => {
  injectNav();
  injectFooter();
  // re-run active link after injection
  const page = window.location.pathname;
  document.querySelectorAll('.nav-links a').forEach(a => {
    if (a.getAttribute('href') === page) a.classList.add('active');
  });
});

/*
 * MindSpace email check for the website signup page.
 * Same rules as the server (api/validators.py) and the mobile app
 * (src/lib/validate.js): a valid shape, plus a check for clearly mistyped
 * domains such as name@g.com, name@gmial.com or name@gmail.con.
 *
 * Usage: window.msEmailProblem(value) -> error message, or null if fine.
 */
(function () {
const EMAIL_RE = /^(?=.{6,254}$)[A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9])?@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$/;

// ── email domain checks (same rules as api/validators.py) ──────────────
// Catches addresses that are valid in shape but clearly mistyped:
// name@g.com, name@gmial.com, name@gmail.con, name@yaho.com ...
const PROVIDERS = {
  gmail: ['gmail.com'],
  hotmail: ['hotmail.com', 'hotmail.co.uk', 'hotmail.co.za', 'hotmail.fr', 'hotmail.de', 'hotmail.it', 'hotmail.es'],
  outlook: ['outlook.com', 'outlook.co.za', 'outlook.co.uk', 'outlook.fr', 'outlook.de', 'outlook.es'],
  icloud: ['icloud.com'],
  yahoo: ['yahoo.com', 'yahoo.co.za', 'yahoo.co.uk', 'yahoo.fr', 'yahoo.de', 'yahoo.es', 'yahoo.it', 'yahoo.ca', 'yahoo.in', 'yahoo.com.au'],
};
const LOOKALIKES_OK = new Set([
  'mail.com', 'email.com', 'googlemail.com', 'gmx.com', 'gmx.net', 'ymail.com', 'aol.com', 'msn.com', 'live.com', 'me.com', 'mac.com',
  'proton.me', 'protonmail.com', 'zoho.com', 'outlook.office365.com',
  'webmail.co.za', 'mweb.co.za', 'telkomsa.net', 'vodamail.co.za', 'absamail.co.za', 'iafrica.com',
]);
const TLD_TYPOS = new Set(['con', 'cmo', 'cpm', 'vom', 'xom', 'ocm', 'comm', 'coom', 'cim', 'clm']);
const SECOND_LEVEL = new Set(['co', 'ac', 'org', 'gov', 'net', 'edu', 'com', 'mil', 'nom', 'web']);

function editDistance(a, b) {
  // Typos needed to turn a into b; swapped neighbours ("gmial") count as one.
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 0; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

function mainLabel(domain) {
  const l = domain.split('.');
  if (l.length >= 3 && SECOND_LEVEL.has(l[l.length - 2]) && l[l.length - 1].length === 2) return l[l.length - 3];
  return l[l.length - 2];
}

function suggest(name, domain) {
  const ending = domain.includes('.') ? domain.slice(domain.indexOf('.') + 1) : 'com';
  const guess = `${name}.${ending}`;
  return PROVIDERS[name].includes(guess) ? guess : `${name}.com`;
}

function emailDomainProblem(email) {
  const [local, domain = ''] = email.toLowerCase().split('@');
  if (LOOKALIKES_OK.has(domain)) return null;
  const label = mainLabel(domain);
  const tld = domain.slice(domain.lastIndexOf('.') + 1);
  if (PROVIDERS[label] && !PROVIDERS[label].includes(domain)) return `Did you mean ${local}@${suggest(label, domain)}?`;
  for (const name of Object.keys(PROVIDERS)) {
    const close = editDistance(label, name) <= (name.length <= 5 ? 1 : 2);
    const shortened = label.length < name.length && name.startsWith(label) && label.length <= 3;
    if (label !== name && (close || shortened)) return `Did you mean ${local}@${suggest(name, domain)}?`;
  }
  if (TLD_TYPOS.has(tld)) return `Did you mean ${local}@${domain.slice(0, -tld.length)}com?`;
  if (label.length < 2) return "That email domain doesn't look right. Check the part after the @.";
  return null;
}


  window.msEmailProblem = function (value) {
    const e = (value || '').trim();
    if (!e) return 'Please enter your email address';
    if (!EMAIL_RE.test(e) || e.includes('..')) return 'Please enter a valid email address, like name@example.com';
    return emailDomainProblem(e);
  };
})();

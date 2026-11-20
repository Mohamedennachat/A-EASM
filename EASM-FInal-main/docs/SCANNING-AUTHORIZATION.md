# Scanning Authorization

This pipeline performs **active, intrusive** scanning (sqlmap attempts SQL
injection; dalfox/xssmap inject XSS payloads; nikto and nuclei probe for
vulnerabilities). Running these against systems you do not own or are not
explicitly authorized to test may be **illegal**.

## Build / demo targets (no separate authorization needed)

The seeded targets in `db/init/02_seed.sql` are publicly hosted apps that are
**explicitly sanctioned for security testing** by their owners:

| Target | Owner / sanction |
|---|---|
| `testfire.net`, `demo.testfire.net` | HCL AltoroMutual, public deliberately-vulnerable demo |
| `ginandjuice.shop` | PortSwigger, public deliberately-vulnerable demo |
| `public-firing-range.appspot.com` | Google, public XSS testbed |
| `scanme.nmap.org` | Nmap project, sanctioned for light scanning |

## Real targets (authorization REQUIRED)

`epita.net` / `epita.fr` (or any production estate) must **only** be scanned with
written authorization. They are deliberately **not** seeded.

Before adding a real domain:
1. Obtain signed authorization (scope, time window, contacts, allowed intensity).
2. Keep the signed PDF with the project records (this is the proposal's
   *"signed Scanning Authorisation"* deliverable).
3. Seed it: `INSERT INTO domains (domain,status,priority) VALUES ('example.org','active',1) ON CONFLICT (domain) DO NOTHING;`
4. Consider starting **passive-only** (subfinder, crt.sh, tlsx, httpx) before
   enabling the active scanners.

---

### Authorization record (fill in & sign)

```
Authorized scope (domains/IPs):  ____________________________________
Excluded systems:                ____________________________________
Authorized window (start–end):   ____________________________________
Max intensity / rate limits:     ____________________________________
Authorizing party (name/role):   ____________________________________
Signature / date:                ____________________________________
Emergency contact:               ____________________________________
```

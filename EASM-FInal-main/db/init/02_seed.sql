-- =====================================================================
--  Seed targets for the build and demo phase only.
--  All entries are publicly reachable AND explicitly sanctioned for
--  active scanning (deliberately-vulnerable demo apps + nmap's scanme).
--
--  epita.net / epita.fr are intentionally NOT seeded here: they are real
--  infrastructure and must only be scanned on an authorized network with
--  the signed scanning-authorization in hand. Add them at test time:
--    INSERT INTO domains (domain, status, priority)
--    VALUES ('epita.net','active',1) ON CONFLICT (domain) DO NOTHING;
-- =====================================================================

INSERT INTO domains (domain, status, priority) VALUES
    ('testfire.net',                     'active', 1),  -- IBM AltoroMutual (SQLi/XSS)
    ('demo.testfire.net',                'active', 1),  -- the live vulnerable host
    ('ginandjuice.shop',                 'active', 1),  -- PortSwigger vuln shop
    ('public-firing-range.appspot.com',  'active', 2),  -- Google XSS testbed
    ('scanme.nmap.org',                  'active', 3)   -- nmap-sanctioned port-scan target
ON CONFLICT (domain) DO NOTHING;

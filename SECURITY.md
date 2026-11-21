# Security and privacy

Never open a public issue containing `user-config.yaml`, `settings.json`, your
Clash subscription URL, passwords, UUIDs, seed files, candidate YAML, firewall
backups, or unredacted logs/screenshots.

The optional desktop island shows your local public IP, proxy exits, country
codes and request timings. Never publish `island-metrics.json`, `current-state.json`,
window state files, or screenshots of a live island without redacting them.
Local-IP discovery intentionally contacts Cloudflare over the physical interface
using an existing excluded endpoint route. Cloudflare sees that source public IP.
The country/region code comes from the same trace response, with no separate
geolocation API. Do not enable this feature if you require no physical-IP probes.

The optional airport fallback intentionally changes the destination-visible IP to
the selected airport when the fixed chain fails its HTTPS health check. It is not
compatible with a requirement that only the fixed IP ever be used. Both features
are off by default and can be enabled separately.

Use a minimal synthetic example with placeholder credentials to report bugs.
For a security issue, prefer the repository's private vulnerability reporting
feature if enabled, or contact a maintainer privately. Do not publish an
unpatched credential-exposure exploit in an issue.

This tool runs with administrator privileges to maintain endpoint host routes.
Review scripts before installing and use a trusted copy. It is not a kill switch
and does not guarantee that all system traffic, IPv6 or DNS cannot bypass a proxy.
Test TCP, UDP, DNS, IPv6 and local connectivity in your own environment.

Uninstallation retains local configuration and backups for recovery. These may
contain secrets and should be removed by their owner when no longer needed.

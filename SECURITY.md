# Security and privacy

Never open a public issue containing `user-config.yaml`, `settings.json`, your
Clash subscription URL, passwords, UUIDs, seed files, candidate YAML, firewall
backups, or unredacted logs/screenshots.

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

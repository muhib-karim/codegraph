# Security

Report a vulnerability through a private GitHub security advisory in this
repository's Security tab, using **Report a vulnerability**. Do not put
sensitive source, credentials or an exploit against a live system in a public
issue. Include the affected version, minimal reproduction, expected behavior
and observed impact. There is no guaranteed response-time commitment.

Security fixes target the latest 1.x release. Earlier versions should be
upgraded before reporting a problem that cannot be reproduced on 1.x.

The MCP server uses local stdio, an existing read-only graph, parameterized
queries and validated repository paths. It has no network listener, arbitrary
Cypher tool, source execution or mutation API. `codegraph index` is a separate
writer that rebuilds the snapshot in place. Stop the MCP server and the
explorer before you run it.

The explorer binds only to loopback, rejects unexpected Host headers and has
no authentication for remote deployment. Do not expose it through a public
proxy. Database metadata and source paths are intended for a trusted local
repository. An actively malicious local writer can race path validation;
filesystem containment is not a general sandbox. Source and symbol text should
be treated as untrusted data by consuming agents and browser interfaces.

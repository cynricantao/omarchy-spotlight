# Security

Omarchy shell plugins run as the logged-in user, not in an application sandbox. Review source before installation and install only from a repository you trust.

## Boundaries

- AI and web activation are explicit user actions. Typing a query does not start an AI session or contact a website.
- Prompt text is passed in argument arrays without shell interpolation. Built-in presets add no permission-bypass flags, but the selected CLI's own configuration still controls its permissions and tools.
- Custom commands are trusted user-supplied programs, not a sandbox. Common direct shell, Python, and Node inline-evaluation forms and environment/privilege-wrapper templates are rejected; this is a guardrail, not a complete interpreter detector. A custom executable or wrapper's internal behavior cannot be proved by this plugin.
- Prompts may be visible in the local process argument list and in the selected CLI's own history. Never enter credentials into queries or custom command templates.
- Native Omarchy menu actions are resolved from trusted installed JSONC plus the user's own extension, never from a result's supplied shell command. Visibility and checkmark conditions are trusted local shell code and are not sandboxed. Review extensions just as you review plugins.
- Native submenu navigation launches no leaf action. Disruptive actions require explicit confirmation; activation rechecks availability and rejects stale action tokens. This prevents accidental dispatch and payload substitution, but is not a security boundary against other programs running as the same user.
- The filename index is private local metadata, not anonymous data. Symlink traversal, unsafe write permissions and unexpected storage ownership are rejected.
- Availability checks do not verify provider authentication, model access or billing. No provider requests are made during normal test runs.

## Report a vulnerability

Use GitHub's **Report a vulnerability** option for this repository. Do not put credentials, private filenames, account data or exploitable details into a public issue. Include the affected commit/version, a minimal synthetic reproduction and the expected boundary.

A passing test suite or marketplace listing is not a security certification. No response-time guarantee is promised.

# Spotlight for Omarchy

A compact native launcher for Omarchy Quattro: **Search or Ask** from one keyboard-first panel.

![Spotlight with demonstration data](preview.png)

*The preview is captured from the real QML interface with isolated demonstration data—not a user's files or desktop.*

## Features

- Search the complete catalog of visible desktop applications; the Apps category is not limited to the mixed-search result cap.
- Find local files and folders by name using a private on-demand index.
- Calculate expressions locally and copy results with Enter.
- Ask an AI CLI in a terminal. General text selects AI first; no prompt is sent while typing.
- Choose Omarchy's default agent, Hermes, Codex, Claude Code, Gemini CLI, OpenCode, or a trusted custom CLI.
- Search the web or open fixed YouTube/GitHub/Google shortcuts on explicit selection.
- Compact icon rail, category tooltips, grouped results and keyboard navigation.
- Browse and search the complete installed Omarchy menu from **Actions**: Apps, Learn, Trigger, Style, Setup, Install, Remove, Update, About and System, including nested submenus.
- Native breadcrumbs, Back navigation, source icons, conditional availability, current-setting checkmarks and confirmation before disruptive actions.

This is an independent community plugin, not an official Omarchy or AI-provider product.

## Requirements

- Omarchy **4.x / Quattro**, with its Quickshell shell and Lua Hyprland configuration. Older Walker/Waybar-based Omarchy versions are not supported.
- Python **3.10+**, `gio`, `xdg-open`, and `wl-copy` on PATH.
- `omarchy-launch-tui` for terminal AI handoff.
- For AI: at least one separately installed and configured supported CLI, or a trusted custom command. **Hermes is optional.** The plugin does not install CLIs, sign into accounts, change models, or configure API credentials.
- Node.js is needed only to run the JavaScript tests, not for normal plugin use.

The plugin runs unsandboxed as your user, like other Omarchy shell plugins. Review the code before enabling it.

## Install

```sh
omarchy plugin add https://github.com/cynricantao/omarchy-spotlight
omarchy plugin enable io.github.cynricantao.spotlight
```

This adds a search button to the bar. You can move it through Omarchy's bar settings or CLI.

### Optional Alt + Space shortcut

Inspect existing bindings first:

```sh
omarchy menu keybindings --print
```

If Alt + Space is free, add this to `~/.config/hypr/bindings.lua`:

```lua
o.bind("ALT + SPACE", "Spotlight", "omarchy-shell shell toggle io.github.cynricantao.spotlight '{}'")
```

If it is already assigned, choose a different shortcut or explicitly unbind the existing assignment before replacing it. Do not leave a local prototype's duplicate binding active.

```sh
hyprctl reload
hyprctl configerrors
```

No installer writes keyboard bindings or replaces your desktop configuration automatically.

## Use

### 1. Open Spotlight

Click the **magnifying-glass search button** in the bar. If you configured the optional shortcut above, you can also press **Alt+Space**. The search field shows **Search or Ask**.

You can open the published plugin from a terminal too:

```sh
omarchy-shell shell summon io.github.cynricantao.spotlight '{}'
```

The command uses the published plugin ID. An older local prototype may use a different ID; use the ID from that prototype's `manifest.json` rather than enabling a second copy accidentally.

### 2. Search or choose a category

Type in the search field, click an icon in the left rail, or use a category shortcut. Hover over an icon to see its name and shortcut.

| Shortcut | Category | What it does |
|---|---|---|
| **Ctrl+1** | All | Mixed results and home suggestions |
| **Ctrl+2** | Apps | Search the complete installed application catalog |
| **Ctrl+3** | Files | Search indexed file and folder names |
| **Ctrl+4** | Web | Search the web on explicit selection |
| **Ctrl+5** | AI | Ask your selected AI CLI in a terminal |
| **Ctrl+6** | Calculate | Calculate locally |
| **Ctrl+7** | Actions | Browse and search the full Omarchy menu |

**Up/Down** selects a result; **Enter** or clicking the result activates it. App results launch the app, file/folder results open it, and calculator results copy the answer. **Escape** closes Spotlight. **Tab / Shift+Tab** cycles categories.

You can also select a route by typing a prefix:

| Input | Behavior |
|---|---|
| `explain DNS` | Ask AI is the default result; matching local items and Web remain alternatives |
| `app firefox` | Search applications only |
| `file invoice` | Search filenames/folder names only |
| `web linux news` | Search DuckDuckGo in the default browser |
| `? explain DNS` | Explicit AI query |
| `= (42 + 8) / 2` | Local calculator; Enter copies the answer |
| `>` | Browse the full Omarchy menu without leaving Spotlight |
| `> screenshot` | Search Omarchy menu actions, labels, aliases and breadcrumb paths |

**Important:** ordinary non-math text selects Ask AI first, even when local matches exist. Use the Apps/Files categories or their prefixes when you want a local result. Nothing is sent to AI or the web merely from typing; selecting that result is what starts the external action.

### 3. Use the full Omarchy menu

1. Open Spotlight and press **Ctrl+7**, click the **lightning-bolt Actions icon**, or type `>`. Categories preserve your search terms; clear any text after `>` to browse the unfiltered menu.
2. You will see **Apps, Learn, Trigger, Style, Setup, Install, Remove, Update, About and System**.
3. Select a category with **Up/Down**, then press **Enter** or click it. Submenus stay inside Spotlight; their rows show a chevron. **Right** also opens regular submenu rows. Apps opens Spotlight's complete application catalog.
4. Keep opening submenus until you reach the command you want. Longer lists scroll; keyboard selection keeps the selected row in view.
5. To go back, press **Alt+Left**, click the **Back arrow**, or press **Backspace** when the Actions query contains only `>` and spaces. Click a breadcrumb to jump directly to that ancestor.
6. To search, type after `>`, for example `> screenshot`. Search is scoped to the current submenu. Click the **Go** root breadcrumb first when you want to search the whole menu.
7. Selecting an Omarchy command opens a confirmation. **Cancel is focused initially**, so another Enter cancels rather than running the command. Click **Continue**, or move focus to Continue with Tab and press Enter, only when you intend to run it. Escape cancels the confirmation.

Examples of menu paths:

| Task | Path inside Actions |
|---|---|
| Read the Omarchy manual | **Learn → Omarchy** |
| Take a screenshot | **Trigger → Capture → Screenshot** |
| Choose a font | **Style → Font → your chosen font**; a checkmark identifies the current font |
| Edit monitor configuration | **Setup → Monitors** |
| Set the default browser | **Setup → Defaults → Browser → an available browser** |
| Install a browser | **Install → Browser → an available choice** |
| Refresh a default configuration | **Update → Config → the configuration**; this resets that configuration, so review before continuing |
| Shut down the computer | **System → Shutdown**; Continue performs the real shutdown |

All Omarchy command leaves currently require confirmation, including informational commands. Normal app/file/calculator/web/AI results keep their existing activation behavior. Package installation/removal, system updates, resets and power commands are **real operations**, not previews. Their own Omarchy tools may ask for more input, authentication or confirmation after Spotlight hands off.

The original Omarchy menu and shortcuts remain available as fallbacks. Installing Spotlight does not automatically replace the built-in menu button or Super+Space binding.

### 4. Choose an AI CLI

Click **AI** in the footer, or press **Ctrl+,**, then select an available CLI. **Omarchy default** follows the system's default agent; another selection changes Spotlight only. See [AI settings](#ai-settings) and [AI setup](AI-SETUP.md) for setup details.

To change the current query to AI mode, press **Ctrl+Enter**; press Enter again to submit it. **Alt+Enter** changes it to Web mode; press Enter again to open the search. These shortcuts do not send the query on their first press.

### If something is missing or does not open

- **Alt+Space does nothing:** use the bar search button and check the [optional shortcut setup](#optional-alt--space-shortcut). The installer does not assign the shortcut automatically.
- **The new Actions menu is missing:** update an existing published installation with `omarchy plugin update io.github.cynricantao.spotlight`, then reopen Spotlight and press Ctrl+7.
- **A menu choice is missing:** availability depends on installed packages and hardware, just like the standard Omarchy menu. An already-installed application may be absent from Install and present under Remove instead.
- **An action reports that it changed or became unavailable:** reopen/reselect the result. Spotlight rechecks the definition before execution; old confirmation is not reused for a changed action.
- **No file match:** Files searches indexed names, not document contents. Check the Files footer for indexing progress, coverage or truncation; the index is intentionally bounded.
- **AI is unavailable:** install and configure a supported CLI separately, then select it in the AI footer. Spotlight does not install agents or sign into accounts for you.
- **Menu-definition/provider error:** review the displayed error and your `~/.config/omarchy/extensions/omarchy-menu.jsonc`. Malformed extensions and unsupported providers are reported, not silently replaced with invented results.

The default home view contains actual installed applications and existing indexed folders. It is not a recent-activity feed and does not invent recency timestamps.

### Omarchy menu coverage

![Native Omarchy menu inside the compact Spotlight panel](menu-preview.png)

*Real native capture of the default root menu; no personal files, prompts or account details are shown.*

Spotlight reads Omarchy's installed `default/omarchy/omarchy-menu.jsonc` and merges your `~/.config/omarchy/extensions/omarchy-menu.jsonc` overrides, matching the standard menu's extension path. It does not bundle a stale copy of the menu or publish your personal extensions. Menu definitions are re-read for queries and activation, so upstream additions and your extensions remain accessible without editing Spotlight. Apps uses the existing complete application catalog; runtime font choices are loaded from Omarchy.

Menu navigation stays in the compact Spotlight panel. Leaf actions use the same Omarchy tools as the standard menu, including their interactive package pickers, configuration editors, authentication and setup dialogs. Spotlight replaces the menu navigation; it does not reimplement those system tools or bypass their own confirmations. Hardware/package conditions can hide entries that do not apply to this computer, just as the standard menu does. Unavailable definitions, malformed extensions, guard failures and unsupported providers are reported rather than disguised as complete results.

Install/removal/update, reset, security/network/boot and power actions require confirmation where applicable. Activation resolves the ID against the current trusted definition, checks availability again and rejects a changed action token rather than executing a command supplied by a result payload. Browsing does not install software, alter networking, reset configuration or run a power action.

Opening Actions does **not** replace the standard Omarchy widget or Super+Space binding automatically. Both can remain as fallbacks; existing Spotlight shortcuts and the seven-category rail are unchanged.

## AI settings

Use the **AI** footer selector. **Omarchy default** follows the agent selected by Omarchy; other choices override it for Spotlight only. Missing executables are identified rather than silently installed or replaced.

The selected CLI keeps its own account, model and permission configuration. The built-in presets add no automatic-approval or sandbox-bypass flags. Login/workspace-trust prompts may require interaction before a CLI processes the first question. Availability on PATH is not proof of authentication or a successful provider connection.

See [AI setup](AI-SETUP.md) for custom argv templates and supported interactive launch forms.

## Privacy and limits

- Search, arithmetic and filename indexing are local. There is no plugin telemetry or automatic AI/web request while typing.
- Menu availability/checkmark discovery evaluates local shell conditions from the trusted installed menu and your own extensions. These are unsandboxed trusted code, not search text; review extensions before adding them. Selecting a leaf action can launch system tools or network operations.
- Selecting Web sends that query to the search engine. Selecting AI hands the query to the chosen CLI, whose own provider, tools, logs and privacy settings apply.
- The plugin stores no query history. Prompts passed to a CLI can appear in the local process argument list; do not put secrets in queries or custom argv configuration.
- File matching is by **filename/folder name**, not file contents or semantic search. Hidden files, symlinks and common generated/dependency directories are excluded.
- The index covers HOME and mounted drives under `/run/media/<user>/`. It refreshes on opening when stale or when mounted roots change; scanning is bounded to 15 seconds or 250,000 names. Coverage and truncation are reported, not silently treated as exhaustive.
- Native arithmetic is supported. **Currency conversion is not included.**

Local data:

| Location | Purpose |
|---|---|
| `$XDG_CACHE_HOME/omarchy-spotlight/` (default `~/.cache/omarchy-spotlight/`) | Private filename index and lock |
| `$XDG_CONFIG_HOME/omarchy/spotlight-ai.json` (default `~/.config/omarchy/spotlight-ai.json`) | Spotlight AI selection and custom argument template |

Storage rejects symlink traversal and unsafe ownership/write permissions rather than changing existing permissions automatically. Resolve an unsafe-path error yourself or choose safe XDG directories; do not make your configuration world-writable.

## Update and remove

```sh
omarchy plugin update io.github.cynricantao.spotlight
omarchy plugin disable io.github.cynricantao.spotlight
omarchy plugin remove io.github.cynricantao.spotlight
```

Remove your optional keybinding separately, then reload and check Hyprland. AI settings and filename-cache paths are separate from the checkout; review them separately if you also want to remove local data.

## Development and verification

```sh
python3 -B -W error::ResourceWarning -m unittest discover -p 'test_*.py' -v
node test_logic.cjs
node test_menu_logic.cjs
omarchy plugin validate .
```

Tests use isolated fixtures for settings, indexing and provider routing. They do not authenticate to an AI provider or prove that every CLI/version works with every account. CLI launch-contract tests, native UI validation, clean-install checks and real provider responses are separate verification layers.

Report reproducible bugs through GitHub issues. Report sensitive vulnerabilities privately; see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for dependency/attribution details. Service and application names belong to their respective owners; no endorsement is implied.

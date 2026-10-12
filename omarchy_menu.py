"""Installed Omarchy menu adapter. Queries never become shell programs.

MenuEngine accepts private source paths and a read-only runner for tests. Public
functions reload definitions on every call; action_argv only plans, never runs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess


def run_readonly(argv, timeout=5):
    """Bound and reap the whole process group, including a timed-out guard."""
    environment = dict(os.environ)
    for key in ('BASH_ENV', 'ENV', 'SHELLOPTS', 'BASHOPTS'):
        environment.pop(key, None)
    with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, env=environment,
                          start_new_session=True, close_fds=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


class MenuError(ValueError):
    """Invalid, unavailable or stale menu selection."""


class GuardError(MenuError):
    def __init__(self, message, guards):
        super().__init__(message)
        # No missing result ever becomes an implicit true. A checked failure
        # also disables its row rather than representing it as unchecked.
        self.results = {(identifier, field):False for identifier, _, _ in guards
                        for field in ('when', 'checked')}


def parse_jsonc(text):
    """Strip comments/trailing commas only outside JSON strings."""
    out, i, quoted = [], 0, False
    while i < len(text):
        char = text[i]
        if quoted:
            out.append(char)
            if char == '\\':
                i += 1
                if i < len(text):
                    out.append(text[i])
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            out.append(char)
        elif text.startswith('//', i):
            end = text.find('\n', i)
            i = len(text) if end < 0 else end
            out.append('\n')
            continue
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            if end < 0:
                raise MenuError('Unterminated JSONC comment')
            out.extend('\n' if c == '\n' else ' ' for c in text[i:end + 2])
            i = end + 2
            continue
        else:
            out.append(char)
        i += 1
    stripped = ''.join(out)
    out, i, quoted = [], 0, False
    while i < len(stripped):
        char = stripped[i]
        if quoted:
            out.append(char)
            if char == '\\':
                i += 1
                if i < len(stripped):
                    out.append(stripped[i])
            elif char == '"':
                quoted = False
        else:
            if char == '"':
                quoted = True
            if char == ',':
                j = i + 1
                while j < len(stripped) and stripped[j].isspace():
                    j += 1
                if j < len(stripped) and stripped[j] in '}]':
                    i += 1
                    continue
            out.append(char)
        i += 1

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise MenuError('Duplicate menu key: ' + key)
            result[key] = value
        return result

    try:
        parsed = json.loads(''.join(out), object_pairs_hook=unique)
    except (ValueError, RecursionError) as exc:
        raise MenuError('Invalid menu JSONC') from exc
    if not isinstance(parsed, dict):
        raise MenuError('Menu source must be an object')
    source = parsed.get('items', parsed)
    if not isinstance(source, dict):
        raise MenuError('Menu items must be an object')
    return source


def source_paths():
    """Honor the official OMARCHY_PATH root, not query/client supplied paths."""
    root = Path(os.environ.get('OMARCHY_PATH') or '/usr/share/omarchy')
    if not root.is_absolute():
        raise MenuError('OMARCHY_PATH must be absolute')
    return (root / 'default/omarchy/omarchy-menu.jsonc',
            Path.home() / '.config/omarchy/extensions/omarchy-menu.jsonc')


def _read_source(path):
    with Path(path).open('r', encoding='utf-8') as handle:
        text = handle.read(4 * 1024 * 1024 + 1)
    if len(text) > 4 * 1024 * 1024:
        raise MenuError('Menu source exceeds size limit')
    return parse_jsonc(text)


def _validate_source(source, extension=False):
    string_fields = {'parent', 'label', 'title', 'icon', 'iconFont', 'description',
                     'action', 'target', 'provider', 'when', 'checked'}
    for identifier, fields in source.items():
        if (not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', identifier)
                or '.__provider__' in identifier):
            raise MenuError('Invalid menu identifier')
        if fields is None and extension and identifier != 'root':
            continue
        if not isinstance(fields, dict):
            raise MenuError('Menu entry must be an object: ' + identifier)
        for field, value in fields.items():
            if field not in string_fields | {'aliases'}:
                raise MenuError('Unknown menu field: ' + field)
            if value is None:
                continue
            if field == 'aliases':
                values = [value] if isinstance(value, str) else value
                if not isinstance(values, list) or any(not isinstance(v, str) or '\x00' in v for v in values):
                    raise MenuError('Menu aliases must be strings')
            elif not isinstance(value, str) or '\x00' in value:
                raise MenuError('Menu field must be a string: ' + field)
        if identifier == 'root' and any(fields.get(f) for f in ('action', 'target', 'provider', 'parent')):
            raise MenuError('Root must be a submenu without a parent')


def load_menu(default_path, extension_path=None):
    merged = _read_source(default_path)
    _validate_source(merged)
    deleted = set()
    if extension_path is not None:
        try:
            extension = _read_source(extension_path)
        except FileNotFoundError:
            extension = {}
        _validate_source(extension, extension=True)
        for identifier, fields in extension.items():
            if fields is None:
                merged.pop(identifier, None)
                deleted.add(identifier)
            elif isinstance(fields, dict):
                prior = merged.get(identifier, {})
                if not isinstance(prior, dict):
                    raise MenuError('Invalid base menu entry')
                merged[identifier] = {**prior, **fields}
            else:
                raise MenuError('Invalid extension entry: ' + identifier)
    entries = {}
    for identifier, fields in merged.items():
        if not isinstance(fields, dict):
            raise MenuError('Invalid menu entry: ' + identifier)
        entry = dict(fields)
        entry['id'] = identifier
        entry['parent'] = fields.get('parent')
        if entry['parent'] is None:
            entry['parent'] = identifier.rsplit('.', 1)[0] if '.' in identifier else 'root'
        for field in ('icon', 'iconFont', 'description', 'action', 'target', 'provider', 'when', 'checked', 'title'):
            entry[field] = fields.get(field) or ''
        entry['label'] = fields.get('label') or identifier
        aliases = fields.get('aliases') or []
        entry['aliases'] = [aliases] if isinstance(aliases, str) else aliases
        if sum(bool(entry[field]) for field in ('action', 'target', 'provider')) > 1:
            raise MenuError('Action, target and provider are mutually exclusive')
        entries[identifier] = entry
    entries.setdefault('root', {'id':'root', 'label':'Go', 'parent':'', 'aliases':[],
                               'action':'', 'target':'', 'provider':'', 'when':'', 'checked':''})
    entries['root']['parent'] = ''
    # A null parent removes its whole subtree, including explicit-parent rows.
    changed = True
    while changed:
        changed = False
        for identifier, entry in list(entries.items()):
            if entry['parent'] in deleted:
                deleted.add(identifier)
                del entries[identifier]
                changed = True
    for identifier in entries:
        chain, current = set(), identifier
        while current:
            if current in chain:
                raise MenuError('Menu parent cycle')
            chain.add(current)
            if current not in entries:
                raise MenuError('Unknown menu parent: ' + current)
            current = entries[current]['parent']
    # Validate all redirects before evaluating any trusted guard; even a link
    # outside the currently displayed scope must not conceal a malformed tree.
    for identifier, entry in entries.items():
        current, seen = identifier, set()
        while entries[current].get('target'):
            if current in seen:
                raise MenuError('Menu target cycle')
            seen.add(current)
            target = entries[current]['target']
            if target not in entries:
                normalized = target.lower().replace('_', '-')
                aliases = [item['id'] for item in entries.values()
                           if any(alias.lower().replace('_', '-') == normalized for alias in item['aliases'])]
                if normalized in ('go', 'menu'):
                    target = 'root'
                elif aliases:
                    target = aliases[0]
                else:
                    raise MenuError('Unknown menu target: ' + target)
            current = target
        if entry.get('target') and entries[current].get('action'):
            raise MenuError('Menu link cannot target a leaf action')
    return entries


class MenuEngine:
    def __init__(self, default_path, extension_path=None, runner=None):
        self.default_path = Path(default_path)
        self.extension_path = extension_path
        self.runner = runner or run_readonly

    def _provider(self, entries, identifier):
        entry = entries[identifier]
        provider = entry.get('provider')
        if not provider or provider == 'apps':
            return ''
        specs = {'fonts': (['omarchy-font-list'], ['omarchy-font-current'], ['omarchy-font-set'], ''),
                 'power-profiles': (['omarchy-powerprofiles-list'], ['powerprofilesctl', 'get'],
                                    ['omarchy-powerprofiles-set', 'autodetect'], '󰐋')}
        if provider not in specs:
            error = 'Unavailable provider: ' + provider
            entry['_provider_error'] = error
            return error
        listing, current_command, setter, icon = specs[provider]
        try:
            listed = self.runner(listing, timeout=3)
            current = self.runner(current_command, timeout=3)
            if listed.returncode or current.returncode or listed.stderr or current.stderr:
                raise MenuError('Provider command failed')
            if len(listed.stdout) > 1024 * 1024 or len(current.stdout) > 8192:
                raise MenuError('Provider output exceeds limit')
            values = list(dict.fromkeys(value for value in listed.stdout.split('\n') if value))
            if any('\x00' in value or '\r' in value for value in values):
                raise MenuError('Invalid provider value')
            active = current.stdout.rstrip('\n')
        except (MenuError, OSError, subprocess.TimeoutExpired) as exc:
            error = 'Unavailable provider ' + provider + ': ' + str(exc)
            entry['_provider_error'] = error
            return error
        for value in values:
            row_id = identifier + '.__provider__' + hashlib.sha256(value.encode()).hexdigest()
            if row_id in entries:
                raise MenuError('Provider row conflicts with menu source')
            entries[row_id] = {'id':row_id, 'parent':identifier, 'label':value,
                              'description':'', 'icon':icon, 'iconFont':'', 'aliases':[],
                              'action':'', 'target':'', 'provider':'', 'when':'', 'checked':'',
                              '_argv':setter + [value], '_checked':value == active,
                              '_providerMenu':identifier}
        return ''

    def _expand_selected(self, entries, identifier):
        if identifier not in entries:
            for entry in list(entries.values()):
                if entry.get('provider') and identifier.startswith(entry['id'] + '.__provider__'):
                    error = self._provider(entries, entry['id'])
                    if error:
                        raise MenuError(error)
                    break

    def _guards(self, entries):
        guards = [(identifier, field, entry[field]) for identifier, entry in entries.items()
                  for field in ('when', 'checked') if entry.get(field)]
        if not guards:
            return {}
        # Parents' visibility must settle before descendants or checkmarks.
        # This also handles explicit-parent extensions declared out of order.
        guards.sort(key=lambda guard: (guard[1] == 'checked',
                                       len(self._ancestors(entries, guard[0]))))
        marker = 'OMARCHY_GUARD_' + secrets.token_hex(16)
        readers = ('omarchy-channel-current', 'omarchy-default-agent', 'omarchy-default-browser',
                   'omarchy-default-editor', 'omarchy-default-terminal', 'omarchy-dns')
        # Executable discovery must not resolve the optional wrapper itself.
        prelude = ('flatpak() { type -P flatpak >/dev/null 2>&1 || return 1; '
                   'command flatpak "$@"; }\n')
        when_indices = {identifier:index for index, (identifier, field, _) in enumerate(guards)
                        if field == 'when'}
        pieces = [prelude]
        for index, (identifier, field, expression) in enumerate(guards):
            required = []
            initializers = []
            for reader_index, reader in enumerate(readers):
                original = '$(' + reader + ')'
                if original not in expression:
                    continue
                slot = '__omarchy_reader_' + str(reader_index)
                expression = expression.replace(original, '${' + slot + '}')
                # Lazy initialization stays in the outer shell, so siblings
                # share one read without initializing readers for hidden rows.
                initializers.append('if [[ ${' + slot + '_loaded:-0} == 0 ]]; then\n'
                                    + slot + '=$(' + reader + ')\n'
                                    + slot + '_code=$?\n' + slot + '_loaded=1\nfi\n')
                required.append(slot + '_code == 0')
            statement = ('(\n' + expression + '\n) >/dev/null 2>/dev/null\n'
                         + '__omarchy_status_' + str(index) + '=$?\n')
            if required:
                statement = (''.join(initializers) + 'if (( ' + ' && '.join(required) + ' )); then\n'
                             + statement + 'else __omarchy_status_' + str(index) + '=125; fi\n')
            applicable = self._ancestors(entries, identifier)
            if field == 'when':
                applicable = applicable[:-1]
            visibility = ['__omarchy_status_' + str(when_indices[parent]) + ' == 0'
                          for parent in applicable if parent in when_indices]
            if visibility:
                statement = ('if (( ' + ' && '.join(visibility) + ' )); then\n' + statement
                             + 'else __omarchy_status_' + str(index) + '=1; fi\n')
            # Numeric indices and a nonce, never source IDs, form the protocol.
            pieces.append(statement + "printf '" + marker + ':' + str(index)
                          + ":%s\\n' \"$__omarchy_status_" + str(index) + '\"\n')
        script = ''.join(pieces)
        try:
            completed = self.runner(['bash', '-c', script], timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GuardError('Menu guard evaluation failed or timed out', guards) from exc
        if completed.returncode or completed.stderr:
            raise GuardError('Menu guard evaluation failed (command or syntax error)', guards)
        results = {}
        lines = completed.stdout.splitlines()
        if len(lines) != len(guards):
            raise GuardError('Incomplete menu guard results', guards)
        for index, line in enumerate(lines):
            match = re.fullmatch(re.escape(marker) + ':' + str(index) + r':([01])', line)
            if not match:
                raise GuardError('Invalid menu guard result', guards)
            results[guards[index][:2]] = match[1] == '0'
        return results

    def _visible(self, entries, identifier, guards, visiting=None):
        visiting = set() if visiting is None else visiting
        if identifier in visiting:
            return False
        entry = entries[identifier]
        if any(not guards.get((p, 'when'), True) for p in self._ancestors(entries, identifier)):
            return False
        if entry.get('action') or entry.get('_argv') or entry.get('provider'):
            return True
        target = self._target(entries, identifier)
        visiting = visiting | {identifier}
        if target != identifier:
            return self._visible(entries, target, guards, visiting)
        return any(self._visible(entries, child['id'], guards, visiting)
                   for child in entries.values() if child['parent'] == identifier)

    @staticmethod
    def _route(entries, identifier):
        if identifier in entries:
            return identifier
        normalized = identifier.lower().replace('_', '-')
        if normalized in ('go', 'menu'):
            return 'root'
        for entry in entries.values():
            if any(alias.lower().replace('_', '-') == normalized for alias in entry['aliases']):
                return entry['id']
        raise MenuError('Unknown menu: ' + identifier)

    def _target(self, entries, identifier):
        seen = set()
        while entries[identifier].get('target'):
            if identifier in seen:
                raise MenuError('Menu target cycle')
            seen.add(identifier)
            identifier = self._route(entries, entries[identifier]['target'])
        return identifier

    @staticmethod
    def _ancestors(entries, identifier):
        result = []
        while identifier:
            result.insert(0, identifier)
            identifier = entries[identifier]['parent']
        return result

    def _row(self, entries, entry, filtered, guards):
        identifier = entry['id']
        target = self._target(entries, identifier)
        final = entries[target]
        kind = ('menu-action' if entry.get('action') or entry.get('_argv') else
                'menu-apps' if final.get('provider') == 'apps' else 'menu')
        parents = self._ancestors(entries, identifier)[:-1]
        subtitle = ' › '.join(entries[p]['label'] for p in parents if p != 'root') if filtered else entry.get('description', '')
        unavailable = final.get('_provider_error', '')
        if final.get('provider') not in ('', None, 'apps', 'fonts', 'power-profiles'):
            unavailable = 'Unavailable provider: ' + final['provider']
        if unavailable and not filtered:
            subtitle = unavailable
        return {'id':'omarchy:' + identifier, 'value':identifier if kind == 'menu-action' else target,
                'kind':kind, 'title':entry['label'], 'subtitle':subtitle,
                'iconKind':'glyph', 'icon':entry.get('icon', ''), 'iconFont':entry.get('iconFont', ''),
                'checked':entry.get('_checked', guards.get((identifier, 'checked'), False)),
                'available':not bool(unavailable), 'unavailableReason':unavailable,
                'requiresConfirmation':kind == 'menu-action',
                'confirmationReason':'This action may change system state' if kind == 'menu-action' else '',
                'actionToken':self._action_token(entries, identifier) if kind == 'menu-action' else ''}

    def _action_token(self, entries, identifier):
        # Also bind the visible title and ancestor guards: a changed definition
        # must be displayed and confirmed again, not retroactively consented to.
        fields = ('id', 'label', 'action', 'parent', 'when', 'provider', 'target', '_argv')
        snapshot = [{field:entries[p].get(field) for field in fields}
                    for p in self._ancestors(entries, identifier)]
        return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=True).encode()).hexdigest()

    def action_argv(self, selected):
        """Reconstruct and authorize a current leaf. No action is executed."""
        if not isinstance(selected, dict) or any(key in selected for key in ('action', 'command', 'argv', 'shell')):
            raise MenuError('Client commands are not accepted')
        identifier = selected.get('value')
        if (not isinstance(identifier, str) or selected.get('id') != 'omarchy:' + identifier
                or selected.get('kind') != 'menu-action'):
            raise MenuError('Invalid action identity')
        entries = load_menu(self.default_path, self.extension_path)
        self._expand_selected(entries, identifier)
        entry = entries.get(identifier)
        if not entry or not (entry.get('action') or entry.get('_argv')):
            raise MenuError('Unknown action or submenu selection')
        token = self._action_token(entries, identifier)
        if selected.get('actionToken') != token:
            raise MenuError('Stale action; select and confirm again')
        # Conservatively require confirmation for every leaf, including custom
        # definitions. Never trust the client requiresConfirmation field.
        if selected.get('confirmed') is not True:
            raise MenuError('Explicit confirmation is required')
        ancestors = {p:entries[p] for p in self._ancestors(entries, identifier)}
        guards = self._guards(ancestors)
        if not self._visible(entries, identifier, guards):
            raise MenuError('Action is no longer available')
        fresh = load_menu(self.default_path, self.extension_path)
        self._expand_selected(fresh, identifier)
        if identifier not in fresh or self._action_token(fresh, identifier) != token:
            raise MenuError('Menu source changed while authorizing action')
        return list(entry['_argv']) if entry.get('_argv') else ['bash', '-c', entry['action']]

    def menu_query(self, query_text, menu_id='root'):
        response = {'query':query_text, 'menu':menu_id, 'items':[], 'breadcrumbs':[], 'status':'error', 'error':''}
        try:
            if not isinstance(query_text, str) or not isinstance(menu_id, str):
                raise MenuError('Query and menu must be strings')
            entries = load_menu(self.default_path, self.extension_path)
            errors = []
            try:
                guards = self._guards(entries)
            except GuardError as exc:
                guards = exc.results
                errors.append(str(exc))
            active = self._target(entries, self._route(entries, menu_id))
            if entries[active].get('action'):
                raise MenuError('An action is not a submenu')
            response['breadcrumbs'] = [{'id':p, 'label':entries[p]['label']}
                                       for p in self._ancestors(entries, active)]
            terms = re.sub(r'^\s*>\s*', '', query_text).casefold().split()
            for entry in list(entries.values()):
                identifier = entry['id']
                if entry.get('provider') and (identifier == active or
                        (terms and active in self._ancestors(entries, identifier)[:-1])):
                    if self._visible(entries, identifier, guards):
                        error = self._provider(entries, identifier)
                        if error:
                            errors.append(error)
            for identifier, entry in entries.items():
                if identifier == 'root':
                    continue
                ancestors = self._ancestors(entries, identifier)
                if active not in ancestors[:-1] or (not terms and entry['parent'] != active):
                    continue
                if not self._visible(entries, identifier, guards):
                    continue
                search = ' '.join([identifier, entry['label'], entry.get('description', ''),
                                   *entry['aliases'], *(entries[p]['label'] for p in ancestors)])
                search = re.sub(r'[._-]', ' ', search.casefold()) + ' ' + search.casefold()
                if all(term in search for term in terms):
                    response['items'].append(self._row(entries, entry, bool(terms), guards))
            response['status'] = ('partial' if response['items'] else 'unavailable') if errors else 'ready'
            response['error'] = '; '.join(errors)
        except (MenuError, OSError, UnicodeError) as exc:
            response.update(items=[], status='error', error=str(exc))
        return response


def menu_query(query_text: str, menu_id: str = 'root') -> dict:
    try:
        return MenuEngine(*source_paths()).menu_query(query_text, menu_id)
    except MenuError as exc:
        return {'query':query_text, 'menu':menu_id, 'items':[], 'breadcrumbs':[], 'status':'error', 'error':str(exc)}


def action_argv(selected: dict) -> list:
    return MenuEngine(*source_paths()).action_argv(selected)

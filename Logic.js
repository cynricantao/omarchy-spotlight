.pragma library

function pointerMoved(previousX, previousY, x, y) {
    return previousX >= 0 && previousY >= 0 && (Math.abs(x - previousX) > 1 || Math.abs(y - previousY) > 1);
}

function acceptResponse(response, currentQuery, opened) {
    return !!opened && !!response && typeof response.query === "string" && response.query === currentQuery;
}

function acceptMenuResponse(response, currentQuery, opened, currentMenu) {
    return acceptResponse(response, currentQuery, opened) && response.menu === currentMenu;
}

function statusTooltipUseful(message, status) {
    return !!message || (!!status && String(status).toLowerCase() !== "ready");
}

function menuTarget(entry) {
    return entry && entry.kind === "menu" && typeof entry.value === "string" ? entry.value : "";
}

function confirmedSelection(entry, accepted) {
    if (accepted !== true || !entry || entry.kind !== "menu-action" || entry.requiresConfirmation !== true) return null;
    var result = {};
    for (var key in entry) if (Object.prototype.hasOwnProperty.call(entry, key)) result[key] = entry[key];
    result.confirmed = true;
    return result;
}

function linkUrl(id) {
    var urls = {youtube:"https://www.youtube.com/", github:"https://github.com/", google:"https://www.google.com/"};
    return Object.prototype.hasOwnProperty.call(urls, id) ? urls[id] : "";
}

function quickLinks() {
    return [
        {id:"youtube", kind:"link", title:"YouTube", subtitle:"youtube.com", icon:"youtube", value:"youtube"},
        {id:"github", kind:"link", title:"GitHub", subtitle:"github.com", icon:"github", value:"github"},
        {id:"google", kind:"link", title:"Google", subtitle:"google.com", icon:"google", value:"google"}
    ];
}

function customAiPayload(text) {
    var argv;
    try { argv = JSON.parse(text); } catch(e) { throw new Error('Enter a JSON argument array, not a shell command.'); }
    if (!Array.isArray(argv) || argv.length < 2 || argv.length > 64) throw new Error('Use an executable followed by its arguments.');
    var count = 0;
    for (var i=0; i<argv.length; i++) {
        if (typeof argv[i] !== 'string' || argv[i].indexOf('\u0000') >= 0 || argv[i].length > 8192) throw new Error('Each argument must be text without NUL characters.');
        count += argv[i].split('{prompt}').length - 1;
    }
    if (!argv[0] || argv[0].indexOf('{prompt}') >= 0 || count !== 1) throw new Error('Put exactly one {prompt} placeholder after the executable.');
    return {provider:'custom',custom_argv:argv};
}

function sectionize(source, category) {
    var items = [], sections = [];
    function add(title, layout, prefix, group) {
        if (!group.length) return;
        var rows = [];
        for (var i=0; i<group.length; i++) {
            rows.push({item:group[i], index:items.length});
            items.push(group[i]);
        }
        sections.push({title:title, layout:layout, prefix:prefix, rows:rows});
    }
    if (category !== "All") {
        add(category, category === "Apps" ? "tiles" : "list", "", source);
        return {items:items, sections:sections};
    }
    if (!source.length) return {items:items, sections:sections};
    add("Top Result", "hero", "", [source[0]]);
    var rest = source.slice(1);
    var groups = [
        {title:"Apps", layout:"tiles", prefix:"app ", kinds:["app"]},
        {title:"Files", layout:"list", prefix:"file ", kinds:["file","folder"]},
        {title:"Web", layout:"tiles", prefix:"web ", kinds:["web","link"]},
        {title:"AI", layout:"list", prefix:"? ", kinds:["ai"]},
        {title:"Calculate", layout:"list", prefix:"= ", kinds:["calculator","calc"]},
        {title:"Actions", layout:"list", prefix:"> ", kinds:["action","menu","menu-action","menu-apps"]}
    ];
    for (var g=0; g<groups.length; g++) {
        var group = groups[g];
        add(group.title, group.layout, group.prefix, rest.filter(function(row) { return group.kinds.indexOf(row.kind)>=0; }));
    }
    return {items:items, sections:sections};
}

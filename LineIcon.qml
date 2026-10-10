import QtQuick

Image {
    id: root
    property string name: "search"
    property color ink: "#b9cbed"
    readonly property var paths: ({
        search: '<circle cx="10.5" cy="10.5" r="6.7"/><path d="m15.6 15.6 5.2 5.2"/>',
        all: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
        app: '<path d="m8 3 12 18M16 3 4 21M2 16h20M9 3l3 5 3-5"/>',
        file: '<path d="M6 2h8l5 5v15H6zM14 2v6h5"/>',
        folder: '<path d="M3 6h7l2 3h9v11H3z"/>',
        web: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 6.5h14M5 17.5h14"/>',
        ai: '<path d="M12 2c1.1 6.8 3.2 8.9 10 10-6.8 1.1-8.9 3.2-10 10C10.9 15.2 8.8 13.1 2 12 8.8 10.9 10.9 8.8 12 2Z"/>',
        calculator: '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 5h8v4H8zM8 13h1m3 0h1m3 0h0M8 17h1m3 0h1m3 0h0"/>',
        action: '<path d="m14 2-10 12h7l-1 8 10-12h-7z"/>',
        return: '<path d="M20 5v6a4 4 0 0 1-4 4H4m5-5-5 5 5 5"/>',
        chevron: '<path d="m9 5 7 7-7 7"/>'
    })
    source: "data:image/svg+xml;charset=utf-8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="'+root.ink+'" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">'+(paths[name] || paths.search)+'</svg>')
    sourceSize.width: Math.round(width * 2)
    sourceSize.height: Math.round(height * 2)
    fillMode: Image.PreserveAspectFit
    smooth: true
}

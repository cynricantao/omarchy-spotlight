import QtQuick
import QtQuick.Controls as Controls

Rectangle {
    id: root
    required property var row
    property string mode: "list"
    property bool selected: false
    property bool compactOverview: false
    property string imageSource: ""
    property string family: "Noto Sans"
    property real scaleFactor: 1
    property string home: ""
    signal activated(int resultIndex)
    signal pointerAt(real px, real py, int resultIndex)
    readonly property var entry: row.item
    readonly property bool tile: mode === "tiles"
    readonly property bool hero: mode === "hero"
    readonly property bool calculation: entry.kind === "calculator"
    readonly property bool glyphIcon: entry.iconKind === "glyph"
    readonly property bool submenu: entry.kind === "menu" || entry.kind === "menu-apps"
    readonly property int iconSize: (hero ? 30 : tile ? 26 : 24) * scaleFactor
    readonly property color ink: "#e7edfa"
    implicitHeight: details.implicitHeight + 14 * scaleFactor
    radius: 7 * scaleFactor
    color: selected ? "#303b57" : pointer.containsMouse ? "#1c253b" : "transparent"
    border.width: selected ? 1 : 0
    border.color: "#4c5a7a"
    Behavior on color { ColorAnimation { duration: 90 } }

    Item {
        id: iconBox
        width: root.iconSize; height: width
        x: (root.tile ? 8 : 10) * root.scaleFactor
        anchors.verticalCenter: parent.verticalCenter
        Image {
            id: nativeIcon
            anchors.fill: parent
            source: root.imageSource
            sourceSize.width: Math.round(width * 2); sourceSize.height: Math.round(height * 2)
            fillMode: Image.PreserveAspectFit; smooth: true
            visible: !root.glyphIcon
        }
        Text {
            anchors.centerIn:parent
            visible:root.glyphIcon
            text:root.entry.icon || ""
            textFormat:Text.PlainText
            font.family:root.entry.iconFont || "CaskaydiaMono Nerd Font"
            font.pixelSize:18*root.scaleFactor
            color:root.selected ? "#a9d3ff" : "#a7b9d9"
        }
        LineIcon {
            anchors.fill: parent
            anchors.margins: root.entry.kind === "ai" ? 5 * root.scaleFactor : 2 * root.scaleFactor
            visible: !root.glyphIcon && nativeIcon.status !== Image.Ready
            name: root.entry.value === "home" ? "folder" : root.entry.kind === "link" ? "web" : root.entry.kind
            ink: "#88b9ff"
        }
    }
    Column {
        id: details
        x: iconBox.x + iconBox.width + 10 * root.scaleFactor
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - x - (root.hero || root.submenu || root.entry.checked ? 44 : 10) * root.scaleFactor
        spacing: 2 * root.scaleFactor
        Text {
            width: parent.width
            text: root.entry.title || ""
            textFormat: Text.PlainText; elide: Text.ElideRight
            font.family: root.family
            font.pixelSize: (root.calculation ? 24 : root.hero ? 15 : 13) * root.scaleFactor
            color: root.ink
        }
        Text {
            width: parent.width
            visible: !root.tile && String(root.entry.subtitle || "").length > 0 && (!root.compactOverview || root.hero || root.calculation)
            text: String(root.entry.subtitle || "").replace(root.home + "/", "~/")
            textFormat: Text.PlainText; elide: root.tile ? Text.ElideRight : Text.ElideMiddle
            font.family: root.family; font.pixelSize: 11 * root.scaleFactor
            color: "#8c9bb8"
        }
    }
    Text {
        anchors.right:parent.right;anchors.rightMargin:14*root.scaleFactor;anchors.verticalCenter:parent.verticalCenter
        visible:root.submenu || root.entry.checked === true
        text:root.entry.checked ? "✓" : "›"
        textFormat:Text.PlainText
        font.family:root.family;font.pixelSize:(root.entry.checked ? 14 : 20)*root.scaleFactor
        color:root.entry.checked ? "#8bcbb5" : "#8999b9"
    }
    Rectangle {
        anchors.right: parent.right; anchors.rightMargin: 10 * root.scaleFactor; anchors.verticalCenter: parent.verticalCenter
        width: 26 * root.scaleFactor; height: width; radius: 6 * root.scaleFactor
        visible: root.hero && root.selected
        color: "#46516d"
        LineIcon { anchors.centerIn: parent; width: 17 * root.scaleFactor; height: width; name: "return"; ink: "#e4ecff" }
    }
    MouseArea {
        id: pointer
        anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
        onPositionChanged: function(mouse) {
            var p = root.mapToItem(null, mouse.x, mouse.y)
            root.pointerAt(p.x, p.y, root.row.index)
        }
        onClicked: root.activated(root.row.index)
    }
    Controls.ToolTip.visible: pointer.containsMouse && String(root.entry.subtitle || "").length > 36
    Accessible.name: root.entry.title || ""
    Accessible.role: Accessible.Button
    Accessible.onPressAction: root.activated(root.row.index)
    Controls.ToolTip.delay: 650
    Controls.ToolTip.text: root.entry.subtitle || ""
}

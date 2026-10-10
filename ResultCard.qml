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
        }
        LineIcon {
            anchors.fill: parent
            anchors.margins: root.entry.kind === "ai" ? 5 * root.scaleFactor : 2 * root.scaleFactor
            visible: nativeIcon.status !== Image.Ready
            name: root.entry.value === "home" ? "folder" : root.entry.kind === "link" ? "web" : root.entry.kind
            ink: "#88b9ff"
        }
    }
    Column {
        id: details
        x: iconBox.x + iconBox.width + 10 * root.scaleFactor
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - x - (root.hero ? 44 : 10) * root.scaleFactor
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
            visible: !root.tile && (!root.compactOverview || root.hero || root.calculation)
            text: String(root.entry.subtitle || "").replace(root.home + "/", "~/")
            textFormat: Text.PlainText; elide: root.tile ? Text.ElideRight : Text.ElideMiddle
            font.family: root.family; font.pixelSize: 11 * root.scaleFactor
            color: "#8c9bb8"
        }
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
    Controls.ToolTip.delay: 650
    Controls.ToolTip.text: root.entry.subtitle || ""
}

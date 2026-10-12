import QtQuick
import QtQuick.Controls as Controls

FocusScope {
    id: root
    property var entry: null
    property real scaleFactor: 1
    property string family: "Noto Sans"
    signal approved()
    signal dismissed()
    visible: entry !== null
    onVisibleChanged: if (visible) Qt.callLater(function() { cancelButton.forceActiveFocus() })
    Keys.onEscapePressed: function(event) { dismissed(); event.accepted = true }

    Rectangle { anchors.fill: parent; color: "#d9101623" }
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
    Rectangle {
        anchors.centerIn: parent
        width: Math.min(460 * root.scaleFactor, parent.width - 40 * root.scaleFactor)
        height: content.implicitHeight + 40 * root.scaleFactor
        radius: 10 * root.scaleFactor
        color: "#192338"; border.width: 1; border.color: "#465d82"
        Column {
            id: content
            x: 20 * root.scaleFactor; y: x; width: parent.width - 2 * x
            spacing: 14 * root.scaleFactor
            Text {
                width: parent.width
                text: root.entry ? root.entry.title : ""
                textFormat: Text.PlainText; wrapMode: Text.WordWrap
                color: "#e6edfc"; font.family: root.family; font.pixelSize: 18 * root.scaleFactor
            }
            Text {
                width: parent.width
                text: root.entry ? root.entry.confirmationReason || "This action can change your system. Continue?" : ""
                textFormat: Text.PlainText; wrapMode: Text.WordWrap
                color: "#a9b9d4"; font.family: root.family; font.pixelSize: 12 * root.scaleFactor
            }
            Row {
                anchors.right: parent.right; spacing: 10 * root.scaleFactor
                Controls.Button {
                    id: cancelButton
                    text: "Cancel"; width: 90 * root.scaleFactor; height: 34 * root.scaleFactor
                    font.family: root.family; font.pixelSize: 12 * root.scaleFactor
                    contentItem: Text { text: cancelButton.text; color: "#e6edfc"; font: cancelButton.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { radius: 6 * root.scaleFactor; color: cancelButton.hovered ? "#364763" : "#26364e"; border.width: cancelButton.activeFocus ? 1 : 0; border.color: "#83bfff" }
                    onClicked: root.dismissed()
                }
                Controls.Button {
                    id: proceedButton
                    text: "Continue"; width: 100 * root.scaleFactor; height: 34 * root.scaleFactor
                    font.family: root.family; font.pixelSize: 12 * root.scaleFactor
                    contentItem: Text { text: proceedButton.text; color: "#ecf3ff"; font: proceedButton.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { radius: 6 * root.scaleFactor; color: proceedButton.hovered ? "#425c86" : "#304b73"; border.width: proceedButton.activeFocus ? 1 : 0; border.color: "#83bfff" }
                    onClicked: root.approved()
                }
            }
        }
    }
}

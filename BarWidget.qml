import QtQuick
import Quickshell
import qs.Ui

BarWidget {
    id: root
    moduleName: "io.github.cynricantao.spotlight"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "\uf002"
        tooltipText: "Spotlight · Alt + Space"
        useActiveColor: false
        onPressed: function(code) {
            Quickshell.execDetached(["omarchy-shell", "shell", "toggle", "io.github.cynricantao.spotlight", "{}"])
        }
    }
}

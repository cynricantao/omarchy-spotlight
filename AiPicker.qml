import QtQuick
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Io
import "Logic.js" as Logic

Item {
    id: root
    property bool active: false
    property real scaleFactor: 1
    property real availableWidth: 600
    property string family: "Noto Sans"
    property var configuration: ({})
    property bool menuOpen: false
    property bool editorOpen: false
    property int menuIndex: 0
    property string errorText: ""
    property string operation: "show"
    property bool refreshQueued: false

    readonly property bool busy: settingsProcess.running
    readonly property string backend: decodeURIComponent(Qt.resolvedUrl("ai_settings.py").toString().replace(/^file:\/\//, ""))
    readonly property var choices: configuration.options || []
    readonly property string selectedLabel: configuration.selected_label || "Choose AI"
    signal restoreSearchFocus()

    function request(args, op) {
        if (settingsProcess.running) { if (op === "show") refreshQueued = true; return }
        operation = op
        settingsProcess.command = ["python3", "-B", backend].concat(args)
        settingsProcess.running = true
    }
    function refresh() { request(["show"], "show") }
    function toggleMenu() {
        editorOpen = false
        menuOpen = !menuOpen
        if (menuOpen) {
            errorText = ""
            menuIndex = Math.max(0, choices.findIndex(function(o) { return o.id === root.configuration.provider }))
            refresh()
            Qt.callLater(function() { menuFocus.forceActiveFocus() })
        } else restoreSearchFocus()
    }
    function dismiss() {
        menuOpen = false; editorOpen = false; errorText = ""
        if (active) restoreSearchFocus()
    }
    function openCustomEditor() {
        if (busy) return
        menuOpen = false; errorText = ""
        var argv = configuration.custom_argv || []
        commandInput.text = argv.length ? JSON.stringify(argv) : ""
        editorOpen = true
        Qt.callLater(function() { commandInput.forceActiveFocus() })
    }
    function selectProvider(provider) {
        if (provider === "custom") { openCustomEditor(); return }
        errorText = ""
        request(["set", JSON.stringify({provider:provider})], "set")
    }
    function saveCustom(text) {
        try {
            var payload = Logic.customAiPayload(text)
            errorText = ""
            request(["set", JSON.stringify(payload)], "set")
        } catch(e) { errorText = String(e.message || e) }
    }
    function summary() {
        return {provider:configuration.provider || "omarchy", selectedLabel:selectedLabel,
            options:choices.map(function(o){return {id:o.id,label:o.label,available:o.available,reason:o.reason}}),
            busy:busy, menuOpen:menuOpen, editorOpen:editorOpen, error:errorText};
    }
    onActiveChanged: {
        if (active) refresh()
        else { menuOpen = false; editorOpen = false }
    }
    Process {
        id: settingsProcess
        stdout: StdioCollector { id: settingsOutput; waitForEnd:true }
        stderr: StdioCollector { waitForEnd:true }
        onExited: function(code) {

            try {
                var reply = JSON.parse(settingsOutput.text)
                if (code === 0 && reply.ok) {
                    root.configuration = reply
                    root.errorText = reply.error || ""
                    if (root.operation === "set") root.dismiss()
                } else root.errorText = reply.error || "Could not read or save AI settings."
            } catch(e) { root.errorText = "AI settings unavailable. Try reopening Spotlight." }
            if (root.refreshQueued) {
                root.refreshQueued = false
                if (root.active) Qt.callLater(root.refresh)
            }
        }
    }

    Rectangle {
        anchors.fill:parent
        radius:5*root.scaleFactor
        color:choiceMouse.containsMouse || root.menuOpen || root.editorOpen ? "#243653" : "#172236"
        border.width:root.menuOpen || root.editorOpen ? 1 : 0
        border.color:"#42658c"
        Text {
            anchors.left:parent.left;anchors.leftMargin:8*root.scaleFactor;anchors.right:chevron.left;anchors.rightMargin:5*root.scaleFactor;anchors.verticalCenter:parent.verticalCenter
            text:"AI: "+root.selectedLabel
            textFormat:Text.PlainText;elide:Text.ElideRight
            font.family:root.family;font.pixelSize:10*root.scaleFactor;color:"#afc6e8"
        }
        LineIcon {id:chevron;anchors.right:parent.right;anchors.rightMargin:7*root.scaleFactor;anchors.verticalCenter:parent.verticalCenter;width:11*root.scaleFactor;height:width;name:"chevron";rotation:root.menuOpen?90:-90;ink:"#afc6e8"}
        MouseArea {id:choiceMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;enabled:!root.busy;onClicked:root.toggleMenu()}
        Controls.ToolTip.visible:choiceMouse.containsMouse && !root.menuOpen && !root.editorOpen
        Controls.ToolTip.delay:400
        Controls.ToolTip.text:"Choose the AI CLI for Spotlight · Ctrl+,"
    }

    Rectangle {
        id: menu
        visible:root.active && root.menuOpen
        x:root.width-width;y:-height-7*root.scaleFactor
        width:Math.min(280*root.scaleFactor,root.availableWidth)
        height:menuColumn.implicitHeight+12*root.scaleFactor
        color:"#182238";border.width:1;border.color:"#425579";radius:8*root.scaleFactor;z:20
        MouseArea{anchors.fill:parent;acceptedButtons:Qt.AllButtons}
        Item {
            id:menuFocus
            anchors.fill:parent
            Keys.onPressed:function(event){
                if(event.key===Qt.Key_Escape){root.dismiss();event.accepted=true}
                else if(event.key===Qt.Key_Down){root.menuIndex=Math.min(root.choices.length-1,root.menuIndex+1);event.accepted=true}
                else if(event.key===Qt.Key_Up){root.menuIndex=Math.max(0,root.menuIndex-1);event.accepted=true}
                else if(event.key===Qt.Key_Return || event.key===Qt.Key_Enter){
                    var choice=root.choices[root.menuIndex]
                    if(choice && (choice.available || choice.id==="custom" || choice.id==="omarchy"))root.selectProvider(choice.id)
                    event.accepted=true
                }
            }
            Column {
                id:menuColumn;x:6*root.scaleFactor;y:6*root.scaleFactor;width:parent.width-12*root.scaleFactor;spacing:2*root.scaleFactor
                Text{text:"AI for Spotlight";width:parent.width;height:23*root.scaleFactor;leftPadding:8*root.scaleFactor;font.family:root.family;font.pixelSize:11*root.scaleFactor;color:"#90a7c9";verticalAlignment:Text.AlignVCenter}
                Repeater {
                    model:root.choices
                    delegate:Rectangle {
                        id:option
                        required property var modelData
                        required property int index
                        readonly property bool usable:modelData.available || modelData.id==="custom" || modelData.id==="omarchy"
                        width:menuColumn.width;height:29*root.scaleFactor;radius:5*root.scaleFactor
                        color:root.menuIndex===index?"#293d5f":"transparent"
                        Text{x:9*root.scaleFactor;anchors.verticalCenter:parent.verticalCenter;text:option.modelData.id==="custom"?"Custom CLI…":option.modelData.label;elide:Text.ElideRight;width:parent.width-84*root.scaleFactor;font.family:root.family;font.pixelSize:12*root.scaleFactor;color:option.usable?"#deebff":"#748199"}
                        Text{anchors.right:parent.right;anchors.rightMargin:8*root.scaleFactor;anchors.verticalCenter:parent.verticalCenter;text:root.configuration.provider===option.modelData.id?"✓":!option.modelData.available && option.modelData.id!=="custom"?"Not found":"";font.family:root.family;font.pixelSize:10*root.scaleFactor;color:"#7799c1"}
                        MouseArea{id:optionMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:option.usable?Qt.PointingHandCursor:Qt.ArrowCursor;onPositionChanged:root.menuIndex=option.index;onClicked:if(option.usable && !root.busy)root.selectProvider(option.modelData.id)}
                        Controls.ToolTip.visible:optionMouse.containsMouse && !option.modelData.available
                        Controls.ToolTip.delay:500
                        Controls.ToolTip.text:option.modelData.reason || "Command not available on PATH"
                    }
                }
                Text{visible:root.errorText!=="";width:parent.width;text:root.errorText;textFormat:Text.PlainText;wrapMode:Text.WordWrap;font.family:root.family;font.pixelSize:10*root.scaleFactor;color:"#efb7a6";padding:6*root.scaleFactor}
            }
        }
    }

    Rectangle {
        id: editor
        visible:root.active && root.editorOpen
        x:root.width-width;y:-height-7*root.scaleFactor
        width:Math.min(550*root.scaleFactor,root.availableWidth)
        height:editorColumn.implicitHeight+24*root.scaleFactor
        color:"#172137";border.width:1;border.color:"#49658c";radius:8*root.scaleFactor;z:30
        MouseArea{anchors.fill:parent;acceptedButtons:Qt.AllButtons}
        Column {
            id:editorColumn;x:12*root.scaleFactor;y:12*root.scaleFactor;width:parent.width-24*root.scaleFactor;spacing:10*root.scaleFactor
            Text{text:"Custom AI CLI";font.family:root.family;font.pixelSize:15*root.scaleFactor;color:"#e0eaff"}
            Text{width:parent.width;text:"Use a trusted installed command and one {prompt} placeholder.\nEnter an argument array, not a shell script. Don’t put credentials here.";wrapMode:Text.WordWrap;font.family:root.family;font.pixelSize:11*root.scaleFactor;color:"#9eb1cd"}
            Controls.ScrollView {
                width:parent.width;height:72*root.scaleFactor
                Controls.TextArea {
                    id:commandInput
                    font.family:"monospace";font.pixelSize:12*root.scaleFactor
                    wrapMode:TextEdit.Wrap
                    color:"#e1eafd";placeholderTextColor:"#8193b2"
                    placeholderText:'["my-ai", "--prompt", "{prompt}"]'
                    selectByMouse:true
                    background:Rectangle{color:"#0e1728";radius:5*root.scaleFactor;border.width:1;border.color:commandInput.activeFocus?"#648fbe":"#344461"}
                    onTextChanged:root.errorText=""
                    Keys.onEscapePressed:root.dismiss()
                }
            }
            Text{visible:root.errorText!=="";width:parent.width;text:root.errorText;textFormat:Text.PlainText;wrapMode:Text.WordWrap;font.family:root.family;font.pixelSize:11*root.scaleFactor;color:"#efb7a6"}
            Row {
                anchors.right:parent.right;spacing:8*root.scaleFactor
                Controls.Button {
                    text:"Cancel";width:65*root.scaleFactor;height:28*root.scaleFactor;enabled:!root.busy
                    contentItem:Text{text:parent.text;horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter;font.family:root.family;font.pixelSize:11*root.scaleFactor;color:"#afc1dc"}
                    background:Rectangle{color:"#26334c";radius:5*root.scaleFactor}
                    onClicked:root.dismiss()
                }
                Controls.Button {
                    text:root.busy?"Saving…":"Save & use";width:91*root.scaleFactor;height:28*root.scaleFactor;enabled:!root.busy
                    contentItem:Text{text:parent.text;horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter;font.family:root.family;font.pixelSize:11*root.scaleFactor;color:"#dfedff"}
                    background:Rectangle{color:"#284a75";radius:5*root.scaleFactor}
                    onClicked:root.saveCustom(commandInput.text)
                }
            }
        }
    }
}

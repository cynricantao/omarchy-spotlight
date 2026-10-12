import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import "Logic.js" as Logic

Item {
    id: root
    property var shell: null
    property var manifest: null
    property string omarchyPath: ""
    property bool opened: false
    property var targetScreen: null
    property var items: []
    property var sections: []
    property int selectedIndex: 0
    property string resultQuery: ""
    property string requestQuery: ""
    property string menuId: "root"
    property string requestMenu: "root"
    property string resultMenu: ""
    property var menuBreadcrumbs: [{id:"root",label:"Omarchy"}]
    property var confirmationPending: null
    property string message: ""
    property string indexStatus: ""
    property bool focusPrimed: false
    property bool keepingOpen: false
    property real pointerX: -1
    property real pointerY: -1
    property bool queuedRefresh: false
    readonly property string home: Quickshell.env("HOME")
    readonly property string backend: decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, ""))
    readonly property string overview: decodeURIComponent(Qt.resolvedUrl("overview.py").toString().replace(/^file:\/\//, ""))
    readonly property bool searching: debounce.running || queryProcess.running
    readonly property string family: "Noto Sans"
    readonly property color ink: "#e6edfc"
    readonly property color muted: "#8999b9"
    readonly property color accent: "#6bbcff"
    readonly property real uiScale: Math.max(0.78, Math.min(1, (panel.width - 48) / 780, (panel.height - 64) / 520))
    readonly property var categories: [
        {name:"All", prefix:"", icon:"all"}, {name:"Apps", prefix:"app ", icon:"app"},
        {name:"Files", prefix:"file ", icon:"file"}, {name:"Web", prefix:"web ", icon:"web"},
        {name:"AI", prefix:"? ", icon:"ai"}, {name:"Calculate", prefix:"= ", icon:"calculator"},
        {name:"Actions", prefix:"> ", icon:"action"}
    ]

    function open(payloadJson) {
        var payload = {}
        try { payload = JSON.parse(payloadJson || "{}") } catch (e) {}
        var monitor = Hyprland.focusedMonitor
        targetScreen = Quickshell.screens.find(function(s) { return monitor && s.name === monitor.name }) || Quickshell.screens[0]
        message = ""; items = []; sections = []; selectedIndex = 0
        menuId = typeof payload.menu === "string" ? payload.menu : "root"
        menuBreadcrumbs = [{id:"root",label:"Omarchy"}]; resultMenu = ""; confirmationPending = null
        focusPrimed = false; pointerX = -1; pointerY = -1
        opened = true
        searchField.text = typeof payload.query === "string" ? payload.query.slice(0,4096) : typeof payload.menu === "string" ? "> " : ""
        debounce.restart()
        if (!indexer.running) indexer.running = true
        focusTimer.restart()
        Qt.callLater(function() { searchField.forceActiveFocus(); searchField.cursorPosition = searchField.text.length })
    }
    function close() {
        opened = false; debounce.stop(); focusTimer.stop(); queuedRefresh = false; confirmationPending = null
        searchField.text = ""; items = []; sections = []; message = ""
    }
    function runQuery() {
        if (!opened) return
        if (queryProcess.running) { queuedRefresh = true; return }
        queuedRefresh = false
        requestQuery = searchField.text
        requestMenu = menuId
        queryProcess.command = category() === "Actions" ? ["python3","-B",backend,"menu-query",requestQuery,requestMenu] : requestQuery === "" ? ["python3","-B",overview] : ["python3","-B",backend,"query",requestQuery]
        queryProcess.running = true
    }
    function changeCategory(prefix) {
        if (confirmationPending) return
        menuId = "root"; resultMenu = ""; menuBreadcrumbs = [{id:"root",label:"Omarchy"}]
        var current = searchField.text.replace(/^(?:app |file |web |\?\s*|=\s*|>\s*)/i, "")
        searchField.text = prefix + current
        debounce.restart()
        searchField.forceActiveFocus()
        searchField.cursorPosition = searchField.text.length
    }
    function category() {
        var s = searchField.text
        if (/^app /i.test(s)) return "Apps"
        if (/^file /i.test(s)) return "Files"
        if (/^web /i.test(s)) return "Web"
        if (/^\?/.test(s)) return "AI"
        if (/^=/.test(s)) return "Calculate"
        if (/^>/.test(s)) return "Actions"
        return "All"
    }
    function choose(index) {
        if (confirmationPending || actionProcess.running || searching || resultQuery !== searchField.text || (category() === "Actions" && resultMenu !== menuId) || index < 0 || index >= items.length) return false
        var entry = items[index]
        var target = Logic.menuTarget(entry)
        if (target) { enterMenu(target); return true }
        if (entry.kind === "menu-apps") { menuId = "root"; searchField.text = "app "; searchField.forceActiveFocus(); return true }
        if (entry.kind === "menu-action" && entry.requiresConfirmation === true) {
            confirmationPending = entry
            return true
        }
        if (entry.kind === "link") {
            var url = Logic.linkUrl(entry.value)
            if (!url) return false
            close()
            Quickshell.execDetached(["xdg-open",url])
            return true
        }
        return dispatchEntry(entry)
    }
    function dispatchEntry(entry) {
        if (actionProcess.running) return false
        keepingOpen = entry.kind === "calculator" || entry.kind === "calc"
        actionProcess.command = ["python3","-B",backend,"activate",JSON.stringify(entry)]
        message = ""
        if (!keepingOpen) opened = false
        actionProcess.running = true
        return true
    }
    function enterMenu(id) {
        if (confirmationPending || actionProcess.running) return
        menuId = id; resultMenu = ""; items = []; sections = []; selectedIndex = 0
        searchField.text = "> "; debounce.restart(); searchField.forceActiveFocus()
        searchField.cursorPosition = searchField.text.length
    }
    function backMenu() {
        if (confirmationPending || category() !== "Actions" || menuId === "root") return
        var previous = menuBreadcrumbs.length > 1 ? menuBreadcrumbs[menuBreadcrumbs.length-2].id : "root"
        enterMenu(previous)
    }
    function dismissConfirmation() {
        confirmationPending = null
        if (opened) searchField.forceActiveFocus()
    }
    function approveConfirmation() {
        var entry = Logic.confirmedSelection(confirmationPending, true)
        confirmationPending = null
        if (entry && opened) dispatchEntry(entry)
    }
    function ensureSelectionVisible() {
        for (var i=0; i<sectionRepeater.count; i++) {
            var section = sectionRepeater.itemAt(i)
            if (!section) continue
            var item = section.resultAt(selectedIndex)
            if (!item) continue
            var p = item.mapToItem(results.contentItem,0,0)
            if (p.y < results.contentY) results.contentY = Math.max(0,p.y-6)
            else if (p.y + item.height > results.contentY + results.height) results.contentY = Math.min(Math.max(0,results.contentHeight-results.height),p.y+item.height-results.height+6)
            return
        }
    }
    function moveSelection(delta) {
        if (!items.length) return
        selectedIndex = (selectedIndex+delta+items.length)%items.length
        ensureSelectionVisible()
    }
    function hoverAt(px,py,index) {
        if (Logic.pointerMoved(pointerX,pointerY,px,py)) selectedIndex=index
        pointerX=px; pointerY=py
    }
    function iconSource(entry) {
        if (entry.iconKind === "glyph") return ""
        if (entry.kind === "folder" || entry.value === "home") return Qt.resolvedUrl("assets/folder-blue.svg").toString()
        if (entry.kind === "ai" || entry.kind === "calculator" || entry.kind === "web") return ""
        var value = entry.value === "home" ? "folder" : String(entry.icon || "")
        if (!value) return ""
        if (value.charAt(0) === "/") return "file://"+value
        if (root.shell && root.shell.appLibrary && entry.kind === "app") return root.shell.appLibrary.iconSource(value)
        return Quickshell.iconPath(value,true)
    }
    function state() {
        return JSON.stringify({design:"compact-v3",nativeMenus:true,menu:menuId,resultMenu:resultMenu,breadcrumbs:menuBreadcrumbs,confirmationPending:confirmationPending ? {id:confirmationPending.id,title:confirmationPending.title} : null,confirmationFocused:confirmation.activeFocus,aiSelector:true,ai:aiPicker.summary(),appsUncapped:true,rounded:true,scrollY:results.contentY,contentHeight:results.contentHeight,viewportHeight:results.height,opened:opened,query:searchField.text,resultQuery:resultQuery,category:category(),items:items,
            sections:sections.map(function(s){return {title:s.title,layout:s.layout,count:s.rows.length}}),selectedIndex:selectedIndex,
            searching:searching,indexing:indexer.running,actionBusy:actionProcess.running,message:message,indexStatus:indexStatus,
            focused:searchField.activeFocus,card:{x:card.x,y:card.y,width:card.width,height:card.height}})
    }

    Timer { id: debounce; interval:130; onTriggered:root.runQuery() }
    Timer { id: focusTimer; interval:80; onTriggered:{root.focusPrimed=true;if(!root.confirmationPending)searchField.forceActiveFocus()} }
    Process {
        id: queryProcess
        stdout: StdioCollector { id:queryOutput;waitForEnd:true }
        stderr: StdioCollector { waitForEnd:true }
        onExited: function(code) {
            try {
                var response=JSON.parse(queryOutput.text)
                if (root.category() === "Actions" ? Logic.acceptMenuResponse(response,searchField.text,root.opened,root.menuId) : Logic.acceptResponse(response,searchField.text,root.opened) && response.menu === undefined) {
                    var rows=response.items || []
                    if (response.query === "" || response.query === "web ") rows=rows.concat(Logic.quickLinks())
                    var layout=Logic.sectionize(rows,root.category())
                    root.items=layout.items;root.sections=layout.sections
                    root.resultQuery=response.query;root.selectedIndex=0
                    if (root.category() === "Actions") { root.resultMenu=response.menu; root.menuBreadcrumbs=response.breadcrumbs || [{id:"root",label:"Omarchy"}] }
                    root.message=/^=\s*$/.test(response.query)?"":response.error || "";root.indexStatus=response.status || ""
                    results.contentY=0
                }
            } catch(e) {
                if (root.requestQuery === searchField.text && root.requestMenu === root.menuId && root.opened) { root.items=[];root.sections=[];root.message="Search helper unavailable. Try reopening Spotlight." }
            }
            if (root.opened && (root.queuedRefresh || root.requestQuery !== searchField.text || root.requestMenu !== root.menuId)) Qt.callLater(root.runQuery)
        }
    }
    Process {
        id:indexer
        command:["python3","-B",root.backend,"index"]
        stdout:StdioCollector { waitForEnd:true }
        stderr:StdioCollector { waitForEnd:true }
        onExited:function(code){if(root.opened)debounce.restart()}
    }
    Process {
        id:actionProcess
        stdout:StdioCollector{id:actionOutput;waitForEnd:true}
        stderr:StdioCollector{waitForEnd:true}
        onExited:function(code){
            var response={ok:false,error:"Could not complete this action."}
            try{response=JSON.parse(actionOutput.text)}catch(e){}
            if(code!==0 || !response.ok){root.opened=true;root.message=response.error || "Could not complete this action.";root.focusPrimed=false;focusTimer.restart()}
            else if(root.keepingOpen){root.message="Copied to clipboard";searchField.forceActiveFocus()}
            else root.close()
        }
    }
    IpcHandler {
        target:"io.github.cynricantao.spotlight"
        function status():string{return root.state()}
        function search(query:string):void{root.open(JSON.stringify({query:query}))}
        function close():void{root.close()}
        function select(index:int):void{root.selectedIndex=Math.max(0,Math.min(root.items.length-1,index));root.ensureSelectionVisible()}
        function activate(index:int):bool{return root.choose(index)}
        function category(index:int):void{if(index>=0 && index<root.categories.length)root.changeCategory(root.categories[index].prefix)}
        function browse(menu:string):void{root.open(JSON.stringify({menu:menu}))}
        function back():void{root.backMenu()}
        function cancelConfirmation():void{root.dismissConfirmation()}
        function aiMenu():void{aiPicker.toggleMenu()}
        function aiSelect(provider:string):void{aiPicker.selectProvider(provider)}
        function aiEdit():void{aiPicker.openCustomEditor()}
        function aiSaveCustom(argvJson:string):void{aiPicker.saveCustom(argvJson)}
        function aiDismiss():void{aiPicker.dismiss()}
    }

    PanelWindow {
        id:panel
        screen:root.targetScreen
        visible:root.opened
        anchors{top:true;bottom:true;left:true;right:true}
        color:"transparent"
        exclusionMode:ExclusionMode.Ignore
        WlrLayershell.namespace:"omarchy-spotlight"
        WlrLayershell.layer:WlrLayer.Overlay
        WlrLayershell.keyboardFocus:root.opened?(root.focusPrimed?WlrKeyboardFocus.OnDemand:WlrKeyboardFocus.Exclusive):WlrKeyboardFocus.None
        onBackingWindowVisibleChanged:if(backingWindowVisible)Qt.callLater(function(){if(!root.confirmationPending)searchField.forceActiveFocus()})
        Rectangle{anchors.fill:parent;color:"#091020";opacity:0.24}
        MouseArea{anchors.fill:parent;onPressed:root.close()}
        Rectangle{x:card.x-5;y:card.y+11;width:card.width+10;height:card.height+10;radius:22*root.uiScale;color:"#33020712"}
        Rectangle { id:roundMask; width:card.width; height:card.height; radius:card.radius; color:"white"; visible:false; layer.enabled:true }
        Rectangle {
            id:card
            width:Math.min(780*root.uiScale,panel.width-48)
            height:Math.min(520*root.uiScale,panel.height-64,Math.max(350*root.uiScale,header.height+footer.height+menuTrail.height+sectionColumn.implicitHeight+22*root.uiScale))
            x:Math.round((panel.width-width)/2)
            y:Math.max(32,Math.round(panel.height*0.18))
            radius:12*root.uiScale
            color:"#111623"
            border.width:1
            border.color:"#4a5b7f"
            clip:true
            layer.enabled:true
            layer.smooth:true
            layer.effect:MultiEffect{maskEnabled:true;maskSource:roundMask;maskThresholdMin:0.5;maskSpreadAtMin:0.15}
            MouseArea{anchors.fill:parent;acceptedButtons:Qt.AllButtons}
            Rectangle {
                id:header
                x:1;y:1;width:parent.width-2;height:56*root.uiScale
                gradient:Gradient{orientation:Gradient.Horizontal;GradientStop{position:0;color:"#191f32"}GradientStop{position:1;color:"#17213a"}}
                LineIcon {x:18*root.uiScale;anchors.verticalCenter:parent.verticalCenter;width:21*root.uiScale;height:width;name:"search";ink:"#b4c9ed"}
                Rectangle{x:52*root.uiScale;anchors.verticalCenter:parent.verticalCenter;width:1;height:24*root.uiScale;color:"#35415e"}
                Controls.TextField {
                    id:searchField
                    x:66*root.uiScale;width:parent.width-x-70*root.uiScale;height:parent.height
                    font.family:root.family;font.pixelSize:20*root.uiScale
                    color:root.ink;placeholderTextColor:"#77849f"
                    placeholderText:"Search or Ask"
                    selectionColor:"#375681";selectedTextColor:"#f0f5ff"
                    background:Item{}
                    maximumLength:4096;selectByMouse:true
                    leftPadding:0;rightPadding:0
                    onTextChanged:{root.items=[];root.sections=[];root.selectedIndex=0;root.message="";if(root.opened)debounce.restart()}
                    Keys.priority:Keys.BeforeItem
                    Keys.onPressed:function(event){
                        if(root.confirmationPending){if(event.key===Qt.Key_Escape)root.dismissConfirmation();event.accepted=true}
                        else if(event.key===Qt.Key_Escape){root.close();event.accepted=true}
                        else if(root.category()==="Actions" && ((event.key===Qt.Key_Left && (event.modifiers & Qt.AltModifier)) || (event.key===Qt.Key_Backspace && /^>\s*$/.test(searchField.text)))){root.backMenu();event.accepted=true}
                        else if(root.category()==="Actions" && event.key===Qt.Key_Right && root.items[root.selectedIndex] && Logic.menuTarget(root.items[root.selectedIndex])){root.choose(root.selectedIndex);event.accepted=true}
                        else if((event.modifiers & Qt.ControlModifier) && event.key===Qt.Key_Comma){aiPicker.toggleMenu();event.accepted=true}
                        else if((event.modifiers & Qt.ControlModifier) && event.key>=Qt.Key_1 && event.key<=Qt.Key_7){root.changeCategory(root.categories[event.key-Qt.Key_1].prefix);event.accepted=true}
                        else if(event.key===Qt.Key_Down){root.moveSelection(1);event.accepted=true}
                        else if(event.key===Qt.Key_Up){root.moveSelection(-1);event.accepted=true}
                        else if(event.key===Qt.Key_Return || event.key===Qt.Key_Enter){
                            if(event.modifiers & Qt.ControlModifier)root.changeCategory("? ")
                            else if(event.modifiers & Qt.AltModifier)root.changeCategory("web ")
                            else root.choose(root.selectedIndex)
                            event.accepted=true
                        }else if(event.key===Qt.Key_Tab){
                            var names=root.categories.map(function(c){return c.name})
                            var step=event.modifiers & Qt.ShiftModifier?-1:1
                            root.changeCategory(root.categories[(names.indexOf(root.category())+step+names.length)%names.length].prefix)
                            event.accepted=true
                        }
                    }
                }
                Rectangle{
                    anchors.right:parent.right;anchors.rightMargin:16*root.uiScale;anchors.verticalCenter:parent.verticalCenter
                    width:36*root.uiScale;height:25*root.uiScale;radius:6*root.uiScale;color:escapeMouse.containsMouse?"#39445f":"#2b3550"
                    Text{anchors.centerIn:parent;text:"Esc";font.family:root.family;font.pixelSize:11*root.uiScale;color:"#e2eaff"}
                    MouseArea{id:escapeMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:root.close()}
                }
                Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:1;color:"#34415e"}
            }
            Rectangle {
                id:sidebar
                x:1;y:header.height+1;width:64*root.uiScale;height:parent.height-y-1
                gradient:Gradient{GradientStop{position:0;color:"#101520"}GradientStop{position:1;color:"#141b2a"}}
                Rectangle{anchors.right:parent.right;width:1;height:parent.height;color:"#29344a"}
                Column {
                    x:10*root.uiScale;y:10*root.uiScale;width:parent.width-20*root.uiScale;spacing:5*root.uiScale
                    Repeater {
                        model:root.categories
                        delegate:Rectangle {
                            id:categoryRow
                            required property var modelData
                            required property int index
                            width:parent.width;height:34*root.uiScale;radius:7*root.uiScale
                            readonly property bool active:root.category()===modelData.name
                            color:active?"#192f54":categoryMouse.containsMouse?"#1b2335":"transparent"
                            border.width:active?1:0;border.color:"#315d97"
                            LineIcon{anchors.centerIn:parent;width:21*root.uiScale;height:width;name:categoryRow.modelData.icon;ink:categoryRow.active?root.accent:"#b7c9eb"}
                            Accessible.name: modelData.name
                            Controls.ToolTip.visible: categoryMouse.containsMouse
                            Controls.ToolTip.delay: 300
                            Controls.ToolTip.text: modelData.name+" · Ctrl "+(index+1)
                            MouseArea{id:categoryMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:root.changeCategory(categoryRow.modelData.prefix)}
                        }
                    }
                }

            }
            Item {
                id:main
                x:sidebar.x+sidebar.width;y:header.height+1;width:parent.width-x-1;height:parent.height-y-1
                Rectangle{anchors.fill:parent;gradient:Gradient{orientation:Gradient.Horizontal;GradientStop{position:0;color:"#141a28"}GradientStop{position:1;color:"#101522"}}}
                Item {
                    id:menuTrail
                    anchors.top:parent.top;anchors.left:parent.left;anchors.right:parent.right
                    height:visible ? 32*root.uiScale : 0
                    visible:root.category()==="Actions"
                    Controls.Button {
                        id:menuBack
                        x:12*root.uiScale;anchors.verticalCenter:parent.verticalCenter
                        width:26*root.uiScale;height:24*root.uiScale
                        enabled:root.menuId!=="root" && !root.confirmationPending
                        text:"‹";font.pixelSize:22*root.uiScale
                        contentItem:Text{text:menuBack.text;color:menuBack.enabled?root.accent:root.muted;font:menuBack.font;horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter}
                        background:Rectangle{radius:5*root.uiScale;color:menuBack.hovered?"#25344e":"transparent"}
                        Accessible.name:"Back to parent menu"
                        Controls.ToolTip.visible:hovered;Controls.ToolTip.text:"Back · Alt+Left"
                        onClicked:root.backMenu()
                    }
                    Row {
                        x:44*root.uiScale;anchors.verticalCenter:parent.verticalCenter;spacing:4*root.uiScale
                        Repeater {
                            model:root.menuBreadcrumbs
                            delegate:Controls.Button {
                                id:crumb
                                required property var modelData
                                required property int index
                                text:(index>0?"›  ":"")+modelData.label
                                height:26*root.uiScale;implicitWidth:contentItem.implicitWidth+12*root.uiScale
                                font.family:root.family;font.pixelSize:11*root.uiScale
                                contentItem:Text{text:crumb.text;textFormat:Text.PlainText;color:crumb.hovered?root.accent:root.muted;font:crumb.font;verticalAlignment:Text.AlignVCenter}
                                background:Rectangle{radius:5*root.uiScale;color:crumb.hovered?"#25344e":"transparent"}
                                onClicked:root.enterMenu(modelData.id)
                            }
                        }
                    }
                }
                Flickable {
                    id:results
                    anchors{top:menuTrail.bottom;left:parent.left;right:parent.right;bottom:footer.top;leftMargin:12*root.uiScale;rightMargin:12*root.uiScale;topMargin:10*root.uiScale;bottomMargin:10*root.uiScale}
                    clip:true;contentWidth:width;contentHeight:sectionColumn.implicitHeight
                    boundsBehavior:Flickable.StopAtBounds
                    Controls.ScrollBar.vertical:Controls.ScrollBar{policy:Controls.ScrollBar.AsNeeded}
                    Column {
                        id:sectionColumn
                        width:results.width;spacing:10*root.uiScale
                        Repeater {
                            id:sectionRepeater
                            model:root.sections
                            delegate:Column {
                                id:group
                                required property var modelData
                                width:sectionColumn.width;spacing:5*root.uiScale
                                function resultAt(index){var i=index-modelData.rows[0].index;return i>=0 && i<rowRepeater.count?rowRepeater.itemAt(i):null}
                                Item{
                                    width:parent.width;height:18*root.uiScale
                                    Text{x:5*root.uiScale;anchors.verticalCenter:parent.verticalCenter;text:root.category()==="Actions" && root.menuBreadcrumbs.length ? root.menuBreadcrumbs[root.menuBreadcrumbs.length-1].label : group.modelData.title;textFormat:Text.PlainText;font.family:root.family;font.pixelSize:12*root.uiScale;color:"#a5b8d8"}
                                    Item{
                                        visible:root.category()==="All" && group.modelData.prefix!==""
                                        anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;width:54*root.uiScale;height:parent.height
                                        Text{anchors.left:parent.left;anchors.verticalCenter:parent.verticalCenter;text:"See all";font.family:root.family;font.pixelSize:10*root.uiScale;color:seeAll.containsMouse?root.accent:root.muted}
                                        LineIcon{anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;width:12*root.uiScale;height:width;name:"chevron";ink:root.muted}
                                        MouseArea{id:seeAll;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:root.changeCategory(group.modelData.prefix)}
                                    }
                                }
                                Grid {
                                    id:resultGrid
                                    width:parent.width
                                    columns:group.modelData.layout==="tiles"?Math.max(1,Math.min(4,Math.floor(width/(155*root.uiScale)))):1
                                    columnSpacing:8*root.uiScale;rowSpacing:2*root.uiScale
                                    Repeater {
                                        id:rowRepeater
                                        model:group.modelData.rows
                                        delegate:ResultCard {
                                            required property var modelData
                                            row:modelData;mode:group.modelData.layout
                                            width:(resultGrid.width-(resultGrid.columns-1)*resultGrid.columnSpacing)/resultGrid.columns
                                            height:Math.max(implicitHeight,(mode==="hero"?52:mode==="tiles"?44:root.category()==="Actions"?33:38)*root.uiScale)
                                            compactOverview:root.category()==="All"
                                            scaleFactor:root.uiScale;family:root.family;home:root.home
                                            selected:root.selectedIndex===modelData.index
                                            imageSource:root.iconSource(modelData.item)
                                            onActivated:function(index){root.choose(index)}
                                            onPointerAt:function(px,py,index){root.hoverAt(px,py,index)}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Column {
                    visible:root.sections.length===0
                    anchors.centerIn:results;width:Math.min(390*root.uiScale,results.width-30);spacing:10*root.uiScale
                    LineIcon{anchors.horizontalCenter:parent.horizontalCenter;width:28*root.uiScale;height:width;name:root.category()==="AI"?"ai":root.category()==="Calculate"?"calculator":"search";ink:"#799dce"}
                    Text{width:parent.width;text:root.searching?"Searching…":root.category()==="AI"?"Ask your AI":root.category()==="Calculate"?"Calculate":root.message?"Check your query":"No results yet";horizontalAlignment:Text.AlignHCenter;font.family:root.family;font.pixelSize:18*root.uiScale;color:root.ink}
                    Text{width:parent.width;text:root.message || (root.category()==="AI"?"Enter opens your question in the AI terminal.":root.category()==="Calculate"?"Try (42 + 8) / 2 or sqrt(81).":"Try an app, filename, or web search.");wrapMode:Text.WordWrap;horizontalAlignment:Text.AlignHCenter;font.family:root.family;font.pixelSize:12*root.uiScale;color:root.muted}
                }
                Rectangle {
                    id:footer
                    z:10
                    anchors.left:parent.left;anchors.right:parent.right;anchors.bottom:parent.bottom;height:32*root.uiScale;color:"#131a2a"
                    Rectangle{width:parent.width;height:1;color:"#2b3750"}
                    Row{
                        x:12*root.uiScale;anchors.verticalCenter:parent.verticalCenter;spacing:14*root.uiScale
                        Repeater{
                            model:[{key:"↑↓",label:"Navigate"},{key:"↵",label:"Select"},root.category()==="Actions"?{key:"‹",label:"Alt+Left back"}:{key:"⇥",label:"Switch tab"}]
                            delegate:Row{
                                required property var modelData
                                spacing:6*root.uiScale
                                Rectangle{width:18*root.uiScale;height:20*root.uiScale;color:"transparent";Text{anchors.centerIn:parent;text:modelData.key;font.family:root.family;font.pixelSize:12*root.uiScale;color:"#a7b8d8"}}
                                Text{anchors.verticalCenter:parent.verticalCenter;text:modelData.label;font.family:root.family;font.pixelSize:10*root.uiScale;color:"#8b9bb9"}
                            }
                        }
                    }
                    Text {
                        anchors.right:aiPicker.visible?aiPicker.left:parent.right;anchors.rightMargin:10*root.uiScale;anchors.verticalCenter:parent.verticalCenter
                        width:Math.max(80*root.uiScale,footer.width-(aiPicker.visible?540:330)*root.uiScale)
                        horizontalAlignment:Text.AlignRight;elide:Text.ElideRight;textFormat:Text.PlainText
                        text:root.message || (root.category()==="Apps" || root.category()==="Actions"?root.indexStatus:indexer.running?"Indexing…":root.category()==="Files"?root.indexStatus:"")
                        font.family:root.family;font.pixelSize:10*root.uiScale;color:root.message?root.accent:"#8a9ab9"
                        MouseArea{id:statusHover;anchors.fill:parent;hoverEnabled:true;acceptedButtons:Qt.NoButton}
                        Controls.ToolTip.visible:statusHover.containsMouse && Logic.statusTooltipUseful(root.message,root.indexStatus)
                        Controls.ToolTip.text:root.message || root.indexStatus
                    }
                    AiPicker {
                        id:aiPicker
                        anchors.right:parent.right;anchors.rightMargin:10*root.uiScale;anchors.verticalCenter:parent.verticalCenter
                        width:210*root.uiScale;height:24*root.uiScale
                        scaleFactor:root.uiScale;family:root.family;availableWidth:footer.width-24*root.uiScale
                        active:root.opened
                        visible:root.category()==="All" || root.category()==="AI" || menuOpen || editorOpen
                        onRestoreSearchFocus:if(root.opened)searchField.forceActiveFocus()
                    }
                }
            }
            MenuConfirmation {
                id:confirmation
                anchors.fill:parent;z:50
                entry:root.confirmationPending
                scaleFactor:root.uiScale;family:root.family
                onDismissed:root.dismissConfirmation()
                onApproved:root.approveConfirmation()
            }
        }
        Rectangle{x:card.x;y:card.y;width:card.width;height:card.height;radius:card.radius;color:"transparent";border.width:1;border.color:"#536589"}
    }
}

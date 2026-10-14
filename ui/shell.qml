import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root
    property string base: Quickshell.env("HYPRASH_ROOT")
    property string state: "ready"
    property string message: "Ready when you are"
    property string transcript: ""
    property real level: 0
    property bool opened: true
    property bool typing: false
    property bool listening: state === "listening" || state === "loading"
    property string lastAction: ""
    property bool actionError: false
    property bool busy: false
    property string activity: "idle"
    property string activityMessage: ""
    property string engine: "Laya · starting"
    property int inferenceMs: 0
    property var lastExecution: ({})
    property bool reducedMotion: Quickshell.env("HYPRASH_REDUCED_MOTION") === "1"
    property var timelineSteps: []
    property string timelinePlanId: ""
    property string timelineStatus: "idle"
    property var pendingApproval: null
    property bool hasApproval: pendingApproval !== null
    property bool expanded: typing || listening || busy || transcript !== "" || state === "error" || actionError || hasApproval || (timelineSteps && timelineSteps.length > 0)
    property string orbMode: engine.indexOf("loading") !== -1 ? "connecting" : busy ? ((activity === "executing" || activity === "acting" || activity === "verifying") ? "working" : "solving") : state === "loading" ? "connecting" : listening ? "listening" : "breathing"
    property string headline: engine.indexOf("loading") !== -1 ? "Loading Laya…" : state === "error" ? "Needs attention" : busy ? ((activity === "executing" || activity === "acting" || activity === "verifying") ? "On it." : activity === "transcribing" ? "Transcribing…" : "Thinking…") : state === "loading" ? "Getting ready…" : listening ? "I’m listening." : "Ready to listen."
    property var theme: ({
  "id": "omarchy", "name": "Omarchy", "followDesktop": true,
  "radius": 2, "controlRadius": 2, "font": "Adwaita Mono", "mode": "dark",
  "background": "#090704", "backgroundTop": "#090704", "backgroundBottom": "#090704",
  "foreground": "#DCB39B", "muted": "#a58674", "accent": "#a4735b",
  "border": "#725f4d", "surface": "#22201d", "hover": "#302e29",
  "success": "#dcbf87", "error": "#cea275", "orb": "#e5c6b4"
})

    function send(data) { backend.write(JSON.stringify(data) + "\n") }
    function toggleMic() {
        if (!backend.running) { state = "error"; message = "Backend unavailable. Restart Hyprash."; return }
        if (listening) send({command: "finish"})
        else if (busy) send({command: "stop"})
        else { transcript = ""; lastAction = ""; pendingApproval = null; timelineSteps = []; send({command: "listen"}) }
    }
    function hide() { send({command: "stop"}); opened = false; typing = false; pendingApproval = null }
    function handle(event) {
        if (event.type === "theme") theme = event.theme
        if (event.type === "activity") { activity = event.state; busy = activity !== "idle"; activityMessage = event.message || "" }
        if (event.type === "engine") engine = event.message
        if (event.type === "decision") inferenceMs = event.elapsed_ms
        if (event.type === "execution") lastExecution = event
        if (event.type === "status") { state = event.state; message = event.message }
        if (event.type === "level") level = event.value
        if (event.type === "transcript" && event.text) transcript = event.text
        if (event.type === "action") { lastAction = event.message; actionError = !!event.error }
        if (event.type === "timeline_update") {
            timelinePlanId = event.plan_id || ""
            timelineStatus = event.status || ""
            timelineSteps = event.steps || []
        }
        if (event.type === "approval_request") pendingApproval = event
        if (event.type === "approval_resolved") pendingApproval = null
        if (event.type === "ui_control") { let result = event.window === "Hyprash · Notes" ? notes.control(event) : camera.control(event); root.send({command: "feedback", message: result}) }
        if (event.type === "note") notes.loadNote(event)
        if (event.type === "camera") { camera.visible = true; if (event.capture) camera.takePhoto() }
    }
    Process {
        id: backend
        command: [root.base + "/.venv/bin/python", "-m", "hyprash.backend"]
        workingDirectory: root.base
        running: true
        stdinEnabled: true
        stdout: SplitParser { onRead: data => { try { root.handle(JSON.parse(data)) } catch (e) { console.warn(e) } } }
        stderr: SplitParser { onRead: data => console.warn(data) }
        onExited: (code, status) => { root.state = "error"; root.message = "Voice service stopped. Restart Hyprash." }
    }
    IpcHandler {
        target: "hyprash"
        function toggle(): void {
            if (root.opened && (root.listening || root.busy)) root.toggleMic()
            else { root.opened = true; if (!root.listening) root.toggleMic() }
        }
        function beginRecording(): void { root.opened = true; root.typing = false; root.transcript = ""; root.lastAction = ""; root.send({command: "listen"}) }
        function finishRecording(): void { root.send({command: "finish"}) }
        function present(): void { root.opened = true }
        function hide(): void { root.hide() }
        function text(value: string): void { root.opened = true; root.send({command: "text", text: value}) }
        function appearance(name: string): void { root.send({command: "theme", name: name}) }
        function approve(approvalId: string): void { root.send({command: "approve", id: approvalId}) }
        function reject(approvalId: string): void { root.send({command: "reject", id: approvalId}) }
        function status(): string { return JSON.stringify({theme: root.theme.id, state: root.state, message: root.message, action: root.lastAction, backend: backend.running, notes: notes.visible, engine: root.engine, activity: root.activity, activityMessage: root.activityMessage, execution: root.lastExecution, orb: root.orbMode, reveal: surface.reveal, inferenceMs: root.inferenceMs, timelineSteps: root.timelineSteps, hasApproval: root.hasApproval}) }
        function quit(): void { root.send({command: "stop"}); Qt.quit() }
    }
    PanelWindow {
        id: panel
        visible: root.opened || surface.reveal > 0.001
        implicitWidth: Math.min(500, screen.width)
        implicitHeight: Math.max(250, root.hasApproval ? 380 : (root.timelineSteps && root.timelineSteps.length > 0) ? 340 : 250)
        mask: Region { item: inputRegion }
        Item {
            id: inputRegion
            x: (panel.width - surface.bodyWidth) / 2
            y: 0
            width: surface.bodyWidth
            height: surface.bodyTop + surface.bodyHeight + 8
        }
        anchors { top: true }
        margins.top: 0
        exclusionMode: ExclusionMode.Ignore
        color: "transparent"
        WlrLayershell.namespace: "hyprash"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: (root.typing || root.hasApproval) ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
        LiquidSurface {
            id: surface
            anchors.fill: parent
            targetWidth: Math.min(root.expanded ? 472 : 436, panel.width - 24)
            targetHeight: root.hasApproval ? ((root.timelineSteps && root.timelineSteps.length > 0) ? 340 : 250) :
                          (root.timelineSteps && root.timelineSteps.length > 0) ? Math.min(280, 142 + root.timelineSteps.length * 28) :
                          (root.typing ? 190 : root.expanded ? 142 : 84)
            reducedMotion: root.reducedMotion
            edge: root.actionError ? root.theme.error : root.busy ? root.theme.accent : root.theme.border
            cornerRadius: root.theme.radius
            backgroundTop: root.theme.backgroundTop
            background: root.theme.background
            backgroundBottom: root.theme.backgroundBottom
            Component.onCompleted: reveal = root.opened ? 1 : 0
            Connections {
                target: root
                function onOpenedChanged() { surface.reveal = root.opened ? 1 : 0 }
            }
        }
        Item {
            x: (panel.width - surface.targetWidth) / 2
            y: surface.bodyTop + (1-surface.contentOpacity)*5
            width: surface.targetWidth
            height: surface.targetHeight
            opacity: surface.contentOpacity
            enabled: surface.reveal > 0.98 && root.opened
            ColumnLayout {
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 16
                anchors.topMargin: 10; anchors.bottomMargin: 13
                spacing: 4
                RowLayout {
                    Layout.fillWidth: true; spacing: 11
                    ThinkingOrb {
                        id: orb
                        Layout.preferredWidth: 64; Layout.preferredHeight: 64
                        tint: root.theme.orb
                        dark: root.theme.mode !== "light"
                        mode: root.orbMode
                        active: panel.visible && surface.reveal > 0.65
                        audioLevel: root.level
                        reducedMotion: root.reducedMotion
                        Accessible.name: "Assistant: " + root.headline
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        RowLayout {
                            spacing: 6
                            Rectangle { width: 4; height: 4; radius: 2; color: root.listening ? root.theme.success : root.theme.muted }
                            Text { text: "HYPRASH  /  LAYA"; color: root.theme.muted; font.family: root.theme.font; font.pixelSize: 9; font.letterSpacing: 1.4 }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: root.headline
                            color: root.theme.foreground; font.family: root.theme.font; font.pixelSize: root.theme.id === "omarchy" ? 15 : 17; font.weight: Font.Medium
                            elide: Text.ElideRight
                        }
                    }
                    ToolButton {
                        text: "▦"; font.pixelSize: 16
                        implicitWidth: 24; implicitHeight: 28; leftPadding: 0; rightPadding: 0
                        palette.buttonText: root.theme.accent
                        ToolTip.visible: root.opened && surface.reveal > 0.99 && (hovered)
                        ToolTip.text: "Theme: " + root.theme.name + ". Click for " + (root.theme.id === "omarchy" ? "Liquid" : "Omarchy")
                        onClicked: root.send({command: "theme", name: root.theme.id === "omarchy" ? "liquid" : "omarchy"})
                    }
                    ToolButton {
                        text: root.typing ? "⌨" : "Aa"; font.family: root.theme.font; font.pixelSize: 12
                        implicitWidth: 25; implicitHeight: 28; leftPadding: 0; rightPadding: 0
                        palette.buttonText: root.theme.muted
                        ToolTip.visible: root.opened && surface.reveal > 0.99 && (hovered); ToolTip.text: "Type a command"
                        onClicked: { root.typing = !root.typing; if (root.typing) input.forceActiveFocus() }
                    }
                    Rectangle {
                        Layout.preferredWidth: 32; Layout.preferredHeight: 32; radius: root.theme.controlRadius
                        color: micMouse.containsMouse ? root.theme.hover : root.theme.surface
                        border.color: root.theme.border
                        Rectangle {
                            anchors.centerIn: parent
                            width: root.listening || root.busy ? 9 : 7
                            height: root.listening || root.busy ? 9 : 12
                            radius: root.listening || root.busy ? 2 : 4
                            color: root.listening ? root.theme.success : root.theme.foreground
                        }
                        Accessible.role: Accessible.Button
                        Accessible.name: root.listening ? "Finish recording and run command" : root.busy ? "Cancel pending actions" : "Start Voxtype recording"
                        MouseArea { id: micMouse; anchors.fill: parent; hoverEnabled: true; onClicked: root.toggleMic() }
                        ToolTip.visible: root.opened && surface.reveal > 0.99 && (micMouse.containsMouse)
                        ToolTip.text: root.listening || root.busy ? (root.listening ? "Finish recording · Ctrl+." : "Cancel") : "Record with Voxtype · Ctrl+."
                    }
                    ToolButton {
                        text: "×"; font.family: root.theme.font; font.pixelSize: 19; implicitWidth: 20; implicitHeight: 28; leftPadding: 0; rightPadding: 0
                        palette.buttonText: root.theme.muted
                        ToolTip.visible: root.opened && surface.reveal > 0.99 && (hovered); ToolTip.text: "Hide and turn microphone off"
                        onClicked: root.hide()
                    }
                }
                Text {
                    visible: root.expanded
                    Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 8
                    Layout.preferredHeight: 38
                    text: root.transcript || (root.listening ? "Speak, then click mic to run · Voxtype" : root.message)
                    color: root.theme.foreground; font.family: root.theme.font; font.pixelSize: 13
                    wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                }
                Text {
                    visible: root.expanded
                    Layout.fillWidth: true; Layout.leftMargin: 12
                    text: root.busy ? (root.activityMessage || "Working…") : (root.lastAction || root.message)
                    color: root.actionError ? root.theme.error : root.theme.muted
                    font.family: root.theme.font; font.pixelSize: 10; elide: Text.ElideRight
                    ToolTip.visible: root.opened && surface.reveal > 0.99 && (actionHover.hovered); ToolTip.text: text
                    HoverHandler { id: actionHover }
                }
                TextField {
                    id: input
                    visible: root.typing; Layout.fillWidth: true; Layout.topMargin: 6
                    placeholderText: "Ask your desktop…"
                    color: root.theme.foreground; placeholderTextColor: root.theme.muted
                    background: Rectangle { color: root.theme.surface; radius: root.theme.controlRadius; border.color: root.theme.border }
                    onAccepted: {
                        if (text.trim()) { root.typing = false; root.send({command: "text", text: text}); text = "" }
                    }
                    Keys.onEscapePressed: root.hide()
                }
                ActionTimeline {
                    id: timelineView
                    Layout.fillWidth: true
                    Layout.leftMargin: 8; Layout.rightMargin: 8
                    theme: root.theme
                    steps: root.timelineSteps
                    planId: root.timelinePlanId
                    overallStatus: root.timelineStatus
                    visible: root.timelineSteps && root.timelineSteps.length > 0
                }
                Rectangle {
                    id: approvalCard
                    visible: root.hasApproval
                    Layout.fillWidth: true
                    Layout.leftMargin: 8; Layout.rightMargin: 8
                    Layout.preferredHeight: 82
                    radius: root.theme.controlRadius || 2
                    color: root.theme.surface || "#22201d"
                    border.color: root.theme.accent || "#fe8019"
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                text: "⚠ APPROVAL REQUIRED"
                                font.pixelSize: 9; font.family: root.theme.font; font.weight: Font.Bold
                                color: root.theme.accent || "#fe8019"
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: "Voice 'approve'/'reject' or click"
                                font.pixelSize: 8; font.family: root.theme.font
                                color: root.theme.muted || "#928374"
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.pendingApproval ? (root.pendingApproval.reason || "Approve action execution?") : ""
                            font.pixelSize: 10; font.family: root.theme.font
                            color: root.theme.foreground || "#d5c4a1"
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Button {
                                id: approveBtn
                                Layout.fillWidth: true
                                text: "Approve (Enter)"
                                font.pixelSize: 10; font.family: root.theme.font
                                palette.buttonText: root.theme.background || "#090704"
                                background: Rectangle {
                                    color: approveBtn.hovered ? (root.theme.foreground || "#d5c4a1") : (root.theme.success || "#8ec07c")
                                    radius: root.theme.controlRadius || 2
                                }
                                onClicked: {
                                    if (root.pendingApproval) {
                                        root.send({command: "approve", id: root.pendingApproval.approval_id});
                                    }
                                }
                            }

                            Button {
                                id: rejectBtn
                                Layout.fillWidth: true
                                text: "Reject (Esc)"
                                font.pixelSize: 10; font.family: root.theme.font
                                palette.buttonText: root.theme.foreground || "#d5c4a1"
                                background: Rectangle {
                                    color: rejectBtn.hovered ? (root.theme.hover || "#302e29") : "transparent"
                                    border.color: root.theme.border || "#725f4d"
                                    radius: root.theme.controlRadius || 2
                                }
                                onClicked: {
                                    if (root.pendingApproval) {
                                        root.send({command: "reject", id: root.pendingApproval.approval_id});
                                    }
                                }
                            }
                        }
                    }

                    focus: root.hasApproval
                    Keys.onReturnPressed: {
                        if (root.pendingApproval) root.send({command: "approve", id: root.pendingApproval.approval_id})
                    }
                    Keys.onEscapePressed: {
                        if (root.pendingApproval) root.send({command: "reject", id: root.pendingApproval.approval_id})
                    }
                }
            }
        }
    }
    Notes {
        id: notes
        theme: root.theme
        onSaveRequested: (id, title, body) => root.send({command: "save_note", id: id, title: title, body: body})
    }
    CameraWindow {
        id: camera
        theme: root.theme
        onFeedback: message => { root.lastAction = message; root.actionError = false }
    }
}

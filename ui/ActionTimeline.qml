import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: timeline
    property var theme
    property var steps: []
    property string planId: ""
    property string overallStatus: "idle"

    implicitHeight: Math.min(steps.length * 28 + 4, 120)
    visible: steps && steps.length > 0

    ListView {
        id: stepList
        anchors.fill: parent
        clip: true
        spacing: 4
        model: timeline.steps
        delegate: Rectangle {
            id: stepRow
            width: stepList.width
            height: 24
            radius: timeline.theme.controlRadius || 2
            color: modelData.status === "running" ? (timeline.theme.hover || "#22201d") :
                   modelData.status === "awaiting_approval" ? (timeline.theme.surface || "#22201d") : "transparent"
            border.color: modelData.status === "awaiting_approval" ? (timeline.theme.accent || "#fe8019") : "transparent"
            border.width: modelData.status === "awaiting_approval" ? 1 : 0

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                spacing: 6

                Text {
                    text: {
                        switch (modelData.status) {
                            case "verified": return "✓";
                            case "failed": return "✗";
                            case "awaiting_approval": return "⚠";
                            case "running": return "▶";
                            case "skipped": return "–";
                            default: return "○";
                        }
                    }
                    font.pixelSize: 11
                    font.family: timeline.theme.font
                    color: {
                        switch (modelData.status) {
                            case "verified": return timeline.theme.success || "#8ec07c";
                            case "failed": return timeline.theme.error || "#fb4934";
                            case "awaiting_approval": return timeline.theme.accent || "#fe8019";
                            case "running": return timeline.theme.foreground || "#fabd2f";
                            default: return timeline.theme.muted || "#928374";
                        }
                    }
                }

                Rectangle {
                    visible: !!modelData.domain
                    radius: 2
                    color: timeline.theme.surface || "#282828"
                    implicitWidth: domainText.implicitWidth + 8
                    implicitHeight: 16
                    Text {
                        id: domainText
                        anchors.centerIn: parent
                        text: (modelData.domain || "").replace("browser:", "").toUpperCase()
                        font.pixelSize: 8
                        font.family: timeline.theme.font
                        color: timeline.theme.muted || "#928374"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: modelData.label || modelData.kind || "Step"
                    font.pixelSize: 10
                    font.family: timeline.theme.font
                    color: modelData.status === "skipped" ? (timeline.theme.muted || "#928374") : (timeline.theme.foreground || "#d5c4a1")
                    elide: Text.ElideRight
                }

                Text {
                    visible: (modelData.duration_ms && modelData.duration_ms > 0) || modelData.requires_approval
                    text: (modelData.duration_ms && modelData.duration_ms > 0) ? (modelData.duration_ms + "ms") : (modelData.requires_approval ? "APPROVAL" : "")
                    font.pixelSize: 8
                    font.family: timeline.theme.font
                    color: modelData.requires_approval ? (timeline.theme.accent || "#fe8019") : (timeline.theme.muted || "#928374")
                }
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell

FloatingWindow {
    id: notes
    required property var theme
    title: "Hyprash · Notes"
    visible: false
    implicitWidth: 660; implicitHeight: 480
    color: theme.background
    property string noteId: ""
    property bool loading: false
    signal saveRequested(string id, string title, string body)
    function loadNote(note) {
        loading = true
        noteId = note.id
        if (titleField.text !== note.title) titleField.text = note.title
        if (bodyField.text !== note.body) bodyField.text = note.body
        loading = false
        visible = true
    }
    function control(task) {
        let target=task.target.toLowerCase().replace(/^(the )/, "").replace(/ (field|button)$/, "")
        if (task.action === "click" && target === "close") { visible = false; return "Closed Notes" }
        let field=(target === "title" || target === "note title") ? titleField : (target === "body" || target === "note body" || target === "text") ? bodyField : null
        if (!field) return "No Notes control named " + task.target
        field.forceActiveFocus()
        if (task.action === "fill") { field.text=task.text; changed(); return "Saved " + target }
        return "Focused " + target
    }
    function changed() { if (!loading && noteId) saveRequested(noteId, titleField.text, bodyField.text) }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 32; spacing: 18
        RowLayout {
            Text { text: "✦  NOTES"; color: theme.accent; font.family: theme.font; font.pixelSize: 12; font.letterSpacing: 2 }
            Item { Layout.fillWidth: true }
            Text { text: "Stored on this device"; color: theme.muted; font.family: theme.font; font.pixelSize: 11 }
            Button { text: "Close"; onClicked: notes.visible = false }
        }
        TextField {
            id: titleField
            Accessible.name: "Note title"
            Layout.fillWidth: true
            color: theme.foreground; font.family: theme.font; font.pixelSize: 30; font.weight: Font.DemiBold
            placeholderText: "Untitled"; background: Item {}
            onTextEdited: notes.changed()
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
        ScrollView {
            Layout.fillHeight: true; Layout.fillWidth: true
            TextArea {
                id: bodyField
                Accessible.name: "Note body"
                color: theme.foreground; font.family: theme.font; font.pixelSize: 16; wrapMode: TextEdit.Wrap
                placeholderText: "Start writing, or say ‘write …’"; placeholderTextColor: theme.muted
                background: Item {}
                onTextChanged: notes.changed()
            }
        }
    }
}

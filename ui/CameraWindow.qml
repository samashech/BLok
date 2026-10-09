import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import Quickshell

FloatingWindow {
    id: window
    title: "Hyprash · Camera"
    implicitWidth: 720; implicitHeight: 500
    color: "#191920"; visible: false
    signal feedback(string message)
    property bool pendingPhoto: false
    property string status: devices.videoInputs.length ? "Camera off" : "No camera connected"
    MediaDevices { id: devices }
    onVisibleChanged: {
        if (visible && devices.videoInputs.length) camera.start()
        else { camera.stop(); pendingPhoto = false; shutter.stop() }
    }
    function takePhoto() {
        if (!devices.videoInputs.length) { status = "No camera connected"; feedback(status); return }
        pendingPhoto = true; status = "Getting ready…"; shutter.restart()
    }
    Timer {
        id: shutter; interval: 1800
        onTriggered: {
            if (!window.visible || !window.pendingPhoto) return
            window.pendingPhoto = false
            if (capture.readyForCapture) capture.captureToFile("")
            else { window.status = "Camera is not ready. Try again."; window.feedback(window.status) }
        }
    }
    CaptureSession {
        camera: Camera {
            id: camera
            cameraDevice: devices.defaultVideoInput
            onErrorOccurred: (error, errorString) => { window.status = errorString; window.feedback(errorString) }
            onActiveChanged: if (active) window.status = "Ready · photos save to Pictures"
        }
        imageCapture: ImageCapture {
            id: capture
            onImageSaved: (id, fileName) => { window.status = "Saved " + fileName; window.feedback(window.status) }
            onErrorOccurred: (id, error, errorString) => { window.status = errorString; window.feedback(errorString) }
        }
        videoOutput: preview
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 14
        RowLayout {
            Text { text: "✦  CAMERA"; color: "#b6a0ff"; font.pixelSize: 12; font.letterSpacing: 2 }
            Item { Layout.fillWidth: true }
            Button { text: "Close"; onClicked: window.visible = false }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            color: "#101014"; radius: 14
            VideoOutput { id: preview; anchors.fill: parent; fillMode: VideoOutput.PreserveAspectFit }
            Text { anchors.centerIn: parent; visible: !camera.active; text: window.status; color: "#b7b1c4" }
        }
        RowLayout {
            Text { Layout.fillWidth: true; text: window.status; color: "#9b9aa9"; font.pixelSize: 11; elide: Text.ElideMiddle }
            Button { text: window.pendingPhoto ? "Get ready…" : "Take photo"; enabled: capture.readyForCapture && !window.pendingPhoto; onClicked: window.takePhoto() }
        }
    }
}

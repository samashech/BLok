import QtQuick
import "ThinkingOrbs.js" as Engine

Canvas {
    id: orb
    width: 64; height: 64
    property string mode: "breathing"
    property bool active: visible
    property bool reducedMotion: false
    property real audioLevel: 0
    property real clock: 0.6
    property real motionSpeed: mode === "breathing" ? 0.35 : 0.75 + audioLevel * 0.5
    renderTarget: Canvas.Image
    onModeChanged: requestPaint()
    onActiveChanged: if (active) requestPaint()
    onPaint: {
        let ctx = getContext("2d")
        ctx.reset()
        ctx.clearRect(0, 0, width, height)
        ctx.scale(width / 64, height / 64)
        Engine.ThinkingOrbs.draw(ctx, mode, clock)
    }
    Timer {
        interval: 33; repeat: true
        running: orb.active && !orb.reducedMotion
        onTriggered: { orb.clock += 0.033 * orb.motionSpeed; orb.requestPaint() }
    }
    Component.onCompleted: requestPaint()
}

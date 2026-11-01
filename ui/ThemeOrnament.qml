import QtQuick

// Seasonal stand-in for the thinking orb: a living ring (diya sparks, flames or
// Minecraft XP pixels) plus a corner badge. It follows the same orb modes, so
// listening and working still read at a glance.
Item {
    id: ornament
    property string kind: ""            // ring style: "sparks" | "arc" | "pixels"
    property string mode: "breathing"   // breathing | listening | solving | working | connecting
    property string badge: ""           // emoji, pixel sprite name, or an image file in the pack
    property string assetBase: ""
    property color primary: "#ffb627"
    property color secondary: "#ffe08a"
    property bool active: true
    property bool reducedMotion: false
    property real t: 0

    readonly property real speed: mode === "listening" ? 2.4 : (mode === "working" || mode === "solving") ? 3.6 : mode === "connecting" ? 0.6 : 1
    readonly property real energy: mode === "listening" ? 1.35 : (mode === "working" || mode === "solving") ? 1.2 : 1

    Timer {
        interval: 40; repeat: true
        running: ornament.active && !ornament.reducedMotion && ornament.visible
        onTriggered: { ornament.t += 0.04 * ornament.speed; ring.requestPaint() }
    }
    onKindChanged: ring.requestPaint()
    onModeChanged: ring.requestPaint()

    function noise(a, b) { return 0.5 + 0.25 * Math.sin(a * 3.1 + b * 1.7) + 0.25 * Math.sin(a * 7.3 - b * 2.9) }

    Canvas {
        id: ring
        anchors.fill: parent
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const cx = width / 2, cy = height / 2, R = Math.min(width, height) / 2 - 9, t = ornament.t, e = ornament.energy
            if (ornament.kind === "sparks") {
                ctx.shadowColor = ornament.primary; ctx.shadowBlur = 6
                ctx.strokeStyle = Qt.rgba(1, 0.75, 0.25, 0.25); ctx.lineWidth = 1
                ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke()
                for (let i = 0; i < 72; i++) {
                    const a = i / 72 * Math.PI * 2
                    const twinkle = 0.5 + 0.5 * Math.sin(t * 3 + i * 1.7)
                    const r = R + (ornament.noise(a * 3, t) - 0.5) * 3
                    ctx.fillStyle = i % 3 ? ornament.primary : ornament.secondary
                    ctx.globalAlpha = 0.35 + 0.65 * twinkle
                    ctx.beginPath(); ctx.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, (0.7 + twinkle * 0.9) * e, 0, Math.PI * 2); ctx.fill()
                    if (i % 6 === 0) {   // sparks flying off the ring
                        const fly = (t * 0.6 + i * 0.13) % 1
                        ctx.globalAlpha = (1 - fly) * 0.9
                        ctx.beginPath(); ctx.arc(cx + Math.cos(a) * (R + 2 + fly * 7 * e), cy + Math.sin(a) * (R + 2 + fly * 7 * e), 0.8, 0, Math.PI * 2); ctx.fill()
                    }
                }
            } else if (ornament.kind === "arc") {
                // Minimal: a thin rind-colored ring with one slow, brighter arc.
                ctx.lineCap = "round"
                ctx.strokeStyle = ornament.primary
                ctx.globalAlpha = 0.35; ctx.lineWidth = 1.5
                ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke()
                const start = t * 0.8
                ctx.globalAlpha = 0.65 + 0.25 * (e - 1) * 3; ctx.lineWidth = 2.5
                ctx.beginPath(); ctx.arc(cx, cy, R, start, start + Math.PI * 0.45 * e); ctx.stroke()
            } else if (ornament.kind === "pixels") {
                // Minimal: one color of square pixels; a soft brightness wave travels around.
                const px = 3
                ctx.fillStyle = ornament.primary
                for (let i = 0; i < 28; i++) {
                    const a = i / 28 * Math.PI * 2
                    const wave = 0.5 + 0.5 * Math.sin(t * 1.6 - i * 0.45)
                    const x = Math.round((cx + Math.cos(a) * R) / px) * px, y = Math.round((cy + Math.sin(a) * R) / px) * px
                    ctx.globalAlpha = 0.25 + 0.45 * wave * e
                    ctx.fillRect(x - px / 2, y - px / 2, px, px)
                }
            }
        }
    }

    // Corner badge: an emoji, or a pixel sprite (pumpkin, creeper, pickaxe).
    readonly property bool imageBadge: /\.(png|svg|webp|jpe?g)$/i.test(badge)
    Image {
        visible: ornament.imageBadge
        source: ornament.imageBadge ? ornament.assetBase + ornament.badge : ""
        width: 22; height: 22; fillMode: Image.PreserveAspectFit; smooth: true
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.rightMargin: -5; anchors.bottomMargin: -4
    }
    Text {
        visible: ornament.badge !== "" && !pixelBadge.known && !ornament.imageBadge
        text: ornament.badge
        font.family: "Noto Color Emoji"; font.pixelSize: 20
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.rightMargin: -6; anchors.bottomMargin: -5
    }
    PixelIcon {
        id: pixelBadge
        readonly property bool known: sprites[ornament.badge] !== undefined
        visible: known
        sprite: ornament.badge
        anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.rightMargin: -4; anchors.bottomMargin: -3
    }
}

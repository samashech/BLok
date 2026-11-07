import QtQuick

// On only while BLoK is listening for you: rings ripple out of the orb and swell
// with your voice. When it stops listening they fade away and the orb goes still.
Item {
    id: rings
    property bool on: false
    property real level: 0
    property color color: "#dcbf87"
    property bool square: false
    property bool reducedMotion: false
    property real phase: 0
    property real swell: level
    width: 64; height: 64
    opacity: on ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 180 } }
    Behavior on swell { NumberAnimation { duration: 90 } }
    NumberAnimation on phase {
        from: 0; to: 1; duration: 1500; loops: Animation.Infinite
        running: rings.on && !rings.reducedMotion
    }
    Repeater {
        model: 3
        Rectangle {
            required property int index
            readonly property real progress: rings.reducedMotion ? 0.5 : (rings.phase + index / 3) % 1
            anchors.centerIn: parent
            width: rings.width * (0.82 + progress * (0.34 + rings.swell * 0.34))
            height: width
            radius: rings.square ? 0 : width / 2
            color: "transparent"
            border.color: rings.color
            border.width: rings.square ? 2 : 1.5
            opacity: (1 - progress) * (0.45 + rings.swell * 0.55)
        }
    }
}

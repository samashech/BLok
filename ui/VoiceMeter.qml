import QtQuick
import QtQuick.Layouts

// How loud BLoK hears you, live: segments fill with your voice, and a word says
// whether that level is good for recognition.
RowLayout {
    id: meter
    property real level: 0              // 0–1, from speech.LevelMeter
    property color low: "#a58674"
    property color good: "#dcbf87"
    property color high: "#cea275"
    property color off: "#302e29"
    property string font: ""
    property bool square: false
    property real shown: level
    readonly property int count: 24
    readonly property string verdict: level < 0.1 ? "" : level < 0.25 ? "Quiet" : level < 0.8 ? "Good" : "Loud"
    spacing: 8
    Behavior on shown { NumberAnimation { duration: 90 } }
    Accessible.name: "Your voice level: " + (verdict || "silent")
    Row {
        spacing: 2
        Repeater {
            model: meter.count
            Rectangle {
                required property int index
                readonly property real position: (index + 0.5) / meter.count
                width: 5; height: 9
                radius: meter.square ? 0 : 1
                color: meter.shown < position ? meter.off : position < 0.25 ? meter.low : position < 0.8 ? meter.good : meter.high
            }
        }
    }
    Text {
        text: meter.verdict
        color: meter.level >= 0.8 ? meter.high : meter.level >= 0.25 ? meter.good : meter.low
        font.family: meter.font; font.pixelSize: 10
    }
}

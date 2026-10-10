import QtQuick
import "LiquidMotion.js" as Motion

// Native port: Libraries.dev's sampled springs + Gaussian/alpha goo merge.
// Only the silhouette is filtered. The text/orb remain a separate crisp layer.
Item {
    id: liquid
    property real reveal: 0
    property real targetWidth: 400
    property real targetHeight: 84
    property bool reducedMotion: false
    property real cornerRadius: 29
    property color backgroundTop: "#15171f"
    property color background: "#0c0e14"
    property color backgroundBottom: "#090b10"
    property color edge: "#434754"
    readonly property real p: Math.max(0, Math.min(1, reveal))
    function segment(a,b) { return Math.max(0,Math.min(1,(p-a)/(b-a))) }
    function smooth(a,b) { let t=segment(a,b); return t*t*(3-2*t) }
    function spring(a,b,bounce) { return Motion.LiquidMotion.spring(segment(a,b),bounce) }
    readonly property real opening: spring(0.28,0.90,true)
    readonly property real bodyWidth: Math.max(16, 46+(targetWidth-46)*Math.min(1.025,opening))
    readonly property real bodyHeight: 36+(targetHeight-36)*spring(0.14,0.78,false)
    readonly property real bodyTop: 18 + 25*Math.sin(Math.PI*smooth(0.02,0.64))
    readonly property real centerY: bodyTop+bodyHeight/2
    readonly property real contentOpacity: smooth(0.77,0.99)
    readonly property real deformation: Math.sin(Math.PI*p)
    readonly property real gooSoftness: 0.45+8.5*(1-smooth(0.70,1))
    readonly property real fluidRadius: Math.min(bodyWidth/2,bodyHeight/2, 40+(cornerRadius-40)*smooth(0.70,1))
    Behavior on reveal { NumberAnimation { duration: liquid.reducedMotion ? 0 : 1150; easing.type: Easing.Linear } }
    Behavior on targetWidth { NumberAnimation { duration: liquid.reducedMotion ? 0 : 480; easing.type: Easing.OutBack; easing.overshoot: 0.65 } }
    Behavior on targetHeight { NumberAnimation { duration: liquid.reducedMotion ? 0 : 480; easing.type: Easing.OutBack; easing.overshoot: 0.65 } }

    Item {
        id: shapes
        anchors.fill: parent
        // The source at the camera and its descending droplet physically merge.
        Rectangle {
            x: (parent.width-width)/2; y: -12
            width: 32*(1-liquid.smooth(0.42,0.72)); height: 30
            radius: width/2; color: "white"
            visible: liquid.p > 0 && width > 0.1
        }
        Rectangle {
            width: 22*(1-liquid.smooth(0.48,0.74)); height: 42
            x: (parent.width-width)/2
            y: 3+17*liquid.smooth(0.03,0.28)
            radius: width/2; color: "white"
            visible: liquid.p > 0 && width > 0.1
        }
        Rectangle {
            x: (parent.width-width)/2
            y: liquid.bodyTop
            width: liquid.bodyWidth; height: liquid.bodyHeight
            radius: liquid.fluidRadius; color: "white"
            scale: liquid.spring(0.0,0.22,false)
            visible: liquid.p > 0
        }
        Repeater {
            model: [-1,1]
            Rectangle {
                required property int modelData
                property real flight: liquid.spring(0.22,0.78,true)
                width: 54+10*liquid.deformation; height: 48+14*liquid.deformation
                x: parent.width/2 + modelData*(liquid.targetWidth/2-30)*flight - width/2
                y: liquid.centerY-height/2 + modelData*10*Math.sin(Math.PI*liquid.segment(0.25,0.8))
                radius: height/2; color: "white"
                scale: liquid.smooth(0.10,0.30)*(1-liquid.smooth(0.66,0.88))
                visible: liquid.p>0 && liquid.p<0.9
            }
        }
    }
    ShaderEffectSource {
        id: raw
        sourceItem: shapes
        hideSource: true
        visible: false
        live: liquid.visible
        textureSize: Qt.size(liquid.width,liquid.height)
    }
    ShaderEffect {
        id: horizontal
        anchors.fill: parent
        property variant source: raw
        property vector2d resolution: Qt.vector2d(width,height)
        property real softness: liquid.gooSoftness
        fragmentShader: Qt.resolvedUrl("shaders/goo-blur.frag.qsb")
    }
    ShaderEffectSource {
        id: blurred
        sourceItem: horizontal
        hideSource: true
        visible: false
        live: liquid.visible
        textureSize: Qt.size(liquid.width,liquid.height)
    }
    ShaderEffect {
        anchors.fill: parent
        visible: liquid.p>0
        property variant source: blurred
        property vector2d resolution: Qt.vector2d(width,height)
        property real softness: liquid.gooSoftness
        property color fillTop: liquid.backgroundTop
        property color fillBottom: liquid.backgroundBottom
        property color rim: liquid.edge
        fragmentShader: Qt.resolvedUrl("shaders/goo-merge.frag.qsb")
    }
    // Resolve to exact theme geometry after the fluid silhouette settles.
    Rectangle {
        x: (parent.width-liquid.bodyWidth)/2
        y: liquid.bodyTop
        width: liquid.bodyWidth; height: liquid.bodyHeight
        radius: liquid.cornerRadius
        opacity: liquid.smooth(0.92,1)
        gradient: Gradient {
            GradientStop { position: 0; color: liquid.backgroundTop }
            GradientStop { position: 1; color: liquid.backgroundBottom }
        }
        border.width: 1
        border.color: liquid.edge
    }

}

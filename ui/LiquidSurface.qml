import QtQuick

// A single changing contour: camera bead → hanging drop → settled island.
Canvas {
    id: liquid
    property real reveal: 0
    property real targetWidth: 400
    property real targetHeight: 84
    property bool reducedMotion: false
    property color edge: "#434754"
    readonly property real p: Math.max(0, Math.min(1, reveal))
    readonly property real spread: smooth(0.12, 0.94, p)
    readonly property real bodyWidth: 8 + (targetWidth - 8) * spread + 12 * Math.sin(p * Math.PI) * Math.sin(p * Math.PI * 3)
    readonly property real bodyHeight: 7 + (targetHeight - 7) * (1 - Math.pow(1-p, 2))
    readonly property real bodyTop: 18 * smooth(0, 0.7, p)
    readonly property real contentOpacity: smooth(0.7, 1, p)
    function smooth(a, b, x) { let t = Math.max(0,Math.min(1,(x-a)/(b-a))); return t*t*(3-2*t) }
    Behavior on reveal { NumberAnimation { duration: liquid.reducedMotion ? 0 : 680; easing.type: Easing.InOutCubic } }
    Behavior on targetWidth { NumberAnimation { duration: liquid.reducedMotion ? 0 : 360; easing.type: Easing.OutCubic } }
    Behavior on targetHeight { NumberAnimation { duration: liquid.reducedMotion ? 0 : 360; easing.type: Easing.OutCubic } }
    onRevealChanged: requestPaint()
    onTargetWidthChanged: requestPaint()
    onTargetHeightChanged: requestPaint()
    onEdgeChanged: requestPaint()
    onPaint: {
        let c = getContext("2d")
        c.reset(); c.clearRect(0,0,width,height)
        if (p < 0.001) return
        let cx=width/2, w=Math.max(8,bodyWidth), h=bodyHeight, top=bodyTop
        let l=cx-w/2, r=cx+w/2, bottom=top+h
        let round=Math.min(h/2,w/2,29)
        let tether=1-smooth(0.70,0.98,p)
        let stem=2.6*tether, join=Math.min(w*0.23, 30)*tether
        let sag=8*Math.sin(Math.PI*p)
        c.globalAlpha = Math.min(1,p*9)
        c.beginPath()
        c.moveTo(cx-stem, top*(1-tether))
        c.bezierCurveTo(cx-stem,top*0.78,cx-join*0.65,top,cx-join,top)
        c.lineTo(l+round,top)
        c.bezierCurveTo(l+round*0.3,top,l,top+round*0.3,l,top+round)
        c.lineTo(l,bottom-round)
        c.bezierCurveTo(l,bottom-round*0.3,l+round*0.3,bottom,l+round,bottom)
        c.bezierCurveTo(cx-w*0.15,bottom+sag,cx+w*0.15,bottom+sag,r-round,bottom)
        c.bezierCurveTo(r-round*0.3,bottom,r,bottom-round*0.3,r,bottom-round)
        c.lineTo(r,top+round)
        c.bezierCurveTo(r,top+round*0.3,r-round*0.3,top,r-round,top)
        c.lineTo(cx+join,top)
        c.bezierCurveTo(cx+join*0.65,top,cx+stem,top*0.78,cx+stem,top*(1-tether))
        c.closePath()
        let fill=c.createLinearGradient(0,0,0,bottom)
        fill.addColorStop(0,"#15171f"); fill.addColorStop(0.5,"#0c0e14"); fill.addColorStop(1,"#090b10")
        c.fillStyle=fill; c.fill()
        c.strokeStyle=edge; c.lineWidth=1; c.stroke()
    }
}

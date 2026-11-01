import QtQuick

// 8×8 pixel-art sprites in the Minecraft style, drawn crisply at any cell size.
Canvas {
    id: icon
    property string sprite: "creeper"
    property real cell: 2.5
    width: cell * 8; height: cell * 8
    onSpriteChanged: requestPaint()
    onCellChanged: requestPaint()

    readonly property var sprites: ({
        // Carved pumpkin: orange rind with ridges, dark carved face.
        "pumpkin": { rows: ["OoOOoOOo", "oOOoOOoO", "OKKOOKKO", "OKKOOKKO", "OOOOOOOO", "OKKKKKKO", "OKOKKOKO", "oOoOOoOo"],
                     colors: { O: "#c8742c", o: "#9a5520", K: "#2a1408" } },
        "creeper": { rows: ["GgGGgGGg", "GGgGGgGG", "gKKGGKKg", "GKKgGKKG", "GGgKKGgG", "gGKKKKGg", "GGKKKKGG", "gGKggKGg"],
                     colors: { G: "#5f9e3a", g: "#4a8530", K: "#0f1a0a" } },
        "pickaxe": { rows: [".SSSS...", "S...WS..", "....W.S.", "...W..S.", "..W.....", ".W......", "W.......", "........"],
                     colors: { S: "#a9a9a9", W: "#8a5d34" } }
    })

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const art = sprites[sprite]
        if (!art) return
        for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) {
            const color = art.colors[art.rows[y][x]]
            if (!color) continue
            ctx.fillStyle = color
            ctx.fillRect(Math.round(x * cell), Math.round(y * cell), Math.ceil(cell), Math.ceil(cell))
        }
    }
}

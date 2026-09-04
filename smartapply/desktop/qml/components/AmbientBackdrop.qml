import QtQuick

Item {
    id: root
    clip: true

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: Theme.canvasLift }
            GradientStop { position: 0.42; color: Theme.canvas }
            GradientStop { position: 1; color: "#07070C" }
        }
    }

    Canvas {
        id: atmosphere
        anchors.fill: parent
        antialiasing: true

        function glow(context, x, y, radius, inner, outer) {
            var gradient = context.createRadialGradient(x, y, 0, x, y, radius)
            gradient.addColorStop(0, inner)
            gradient.addColorStop(1, outer)
            context.fillStyle = gradient
            context.fillRect(x - radius, y - radius, radius * 2, radius * 2)
        }

        onPaint: {
            var context = getContext("2d")
            context.clearRect(0, 0, width, height)
            glow(context, width * 0.86, height * 0.02, Math.max(420, width * 0.48), "rgba(116, 88, 255, 0.13)", "rgba(116, 88, 255, 0)")
            glow(context, width * 0.38, height * 0.92, Math.max(380, width * 0.38), "rgba(69, 48, 156, 0.08)", "rgba(69, 48, 156, 0)")
            glow(context, width * 1.02, height * 0.78, Math.max(300, width * 0.30), "rgba(129, 96, 255, 0.06)", "rgba(129, 96, 255, 0)")

            context.fillStyle = "rgba(207, 198, 255, 0.055)"
            for (var x = width * 0.58; x < width; x += 42) {
                for (var y = 24; y < height * 0.54; y += 42) {
                    context.beginPath()
                    context.arc(x, y, 0.7, 0, Math.PI * 2)
                    context.fill()
                }
            }
        }

        Component.onCompleted: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 1
        color: "#0CFFFFFF"
    }
}

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

    // Keep the atmosphere GPU-cheap: a few static shapes replace the large
    // Canvas that was repainted whenever a page was resized or animated.
    Rectangle {
        width: Math.max(360, parent.width * 0.46)
        height: width
        radius: width / 2
        x: parent.width * 0.72
        y: -height * 0.72
        color: "#04765FFF"
    }
    Rectangle {
        width: Math.max(300, parent.width * 0.34)
        height: width
        radius: width / 2
        x: parent.width * 0.18
        y: parent.height * 0.82
        color: "#0349349E"
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 1
        color: "#0CFFFFFF"
    }
}

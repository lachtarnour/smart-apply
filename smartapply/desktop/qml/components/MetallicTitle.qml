import QtQuick

Item {
    id: root

    property string text: ""
    property color baseColor: "#87858E"
    property int pixelSize: 32
    property real letterSpacing: -1.05
    property real sheenPosition: -84
    readonly property real paintedTitleWidth: Math.min(width, titleBase.implicitWidth)

    implicitWidth: titleBase.implicitWidth
    implicitHeight: titleBase.implicitHeight
    clip: true

    function resetSheen() {
        sheenPosition = -84
        sheen.restart()
    }

    onVisibleChanged: if (visible) resetSheen()
    onWidthChanged: if (visible && width > 0) resetSheen()

    Text {
        id: titleShadow
        anchors.fill: parent
        anchors.topMargin: 3
        text: root.text
        color: "#E0000000"
        font.family: Theme.fontFamily
        font.pixelSize: root.pixelSize
        font.weight: Font.Bold
        font.letterSpacing: root.letterSpacing
        renderType: Text.NativeRendering
        elide: Text.ElideRight
    }

    Text {
        id: titleBase
        anchors.fill: parent
        text: root.text
        color: root.baseColor
        font.family: Theme.fontFamily
        font.pixelSize: root.pixelSize
        font.weight: Font.Bold
        font.letterSpacing: root.letterSpacing
        renderType: Text.NativeRendering
        elide: Text.ElideRight
    }

    Item {
        id: polishedCrown
        x: 0
        y: 0
        width: root.width
        height: Math.round(root.height * 0.4)
        clip: true
        opacity: 0.8
        Text {
            x: 0
            y: 0
            width: root.width
            height: root.height
            text: root.text
            color: "#F3F2F5"
            font.family: Theme.fontFamily
            font.pixelSize: root.pixelSize
            font.weight: Font.Bold
            font.letterSpacing: root.letterSpacing
            renderType: Text.NativeRendering
            elide: Text.ElideRight
        }
    }

    Item {
        id: specularRidge
        x: 0
        y: Math.round(root.height * 0.2)
        width: root.width
        height: Math.max(2, Math.round(root.height * 0.08))
        clip: true
        opacity: 0.82
        Text {
            x: 0
            y: -specularRidge.y
            width: root.width
            height: root.height
            text: root.text
            color: "#FFFFFF"
            font.family: Theme.fontFamily
            font.pixelSize: root.pixelSize
            font.weight: Font.Bold
            font.letterSpacing: root.letterSpacing
            renderType: Text.NativeRendering
            elide: Text.ElideRight
        }
    }

    Item {
        id: marbleVein
        x: 0
        y: Math.round(root.height * 0.46)
        width: root.width
        height: Math.max(3, Math.round(root.height * 0.09))
        clip: true
        opacity: 0.54
        Text {
            x: 0
            y: -marbleVein.y
            width: root.width
            height: root.height
            text: root.text
            color: "#4B4A52"
            font.family: Theme.fontFamily
            font.pixelSize: root.pixelSize
            font.weight: Font.Bold
            font.letterSpacing: root.letterSpacing
            renderType: Text.NativeRendering
            elide: Text.ElideRight
        }
    }

    Item {
        id: pearlEdge
        x: 0
        y: Math.round(root.height * 0.65)
        width: root.width
        height: root.height - y
        clip: true
        opacity: 0.58
        Text {
            x: 0
            y: -pearlEdge.y
            width: root.width
            height: root.height
            text: root.text
            color: "#CFCDD3"
            font.family: Theme.fontFamily
            font.pixelSize: root.pixelSize
            font.weight: Font.Bold
            font.letterSpacing: root.letterSpacing
            renderType: Text.NativeRendering
            elide: Text.ElideRight
        }
    }

    Item {
        id: movingReflection
        x: root.sheenPosition
        y: 0
        width: 58
        height: root.height
        clip: true
        Repeater {
            model: [
                {offset: 0, width: 16, opacity: 0.2},
                {offset: 16, width: 26, opacity: 0.98},
                {offset: 42, width: 16, opacity: 0.28}
            ]
            delegate: Item {
                required property var modelData
                x: modelData.offset
                y: 0
                width: modelData.width
                height: movingReflection.height
                clip: true
                opacity: modelData.opacity
                Text {
                    x: -(movingReflection.x + modelData.offset)
                    y: 0
                    width: root.width
                    height: root.height
                    text: root.text
                    color: "#FFFFFF"
                    font.family: Theme.fontFamily
                    font.pixelSize: root.pixelSize
                    font.weight: Font.Bold
                    font.letterSpacing: root.letterSpacing
                    renderType: Text.NativeRendering
                    elide: Text.ElideRight
                }
            }
        }
    }

    Item {
        id: glint
        x: Math.min(root.width - width, root.paintedTitleWidth + 7)
        y: 3
        width: 13
        height: 13
        opacity: 0
        Rectangle {
            anchors.centerIn: parent
            width: 2
            height: parent.height
            radius: 1
            color: "#F8F8FF"
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width
            height: 2
            radius: 1
            color: "#F8F8FF"
        }
        SequentialAnimation on opacity {
            loops: Animation.Infinite
            PauseAnimation { duration: 1450 }
            NumberAnimation { from: 0; to: 0.95; duration: 160; easing.type: Easing.OutCubic }
            NumberAnimation { from: 0.95; to: 0; duration: 420; easing.type: Easing.InCubic }
            PauseAnimation { duration: 3970 }
        }
    }

    SequentialAnimation {
        id: sheen
        running: root.visible && root.width > 0
        loops: Animation.Infinite
        PauseAnimation { duration: 650 }
        NumberAnimation {
            target: root
            property: "sheenPosition"
            from: -84
            to: root.paintedTitleWidth + 50
            duration: 1150
            easing.type: Easing.InOutCubic
        }
        PauseAnimation { duration: 3750 }
        PropertyAction { target: root; property: "sheenPosition"; value: -84 }
    }
}

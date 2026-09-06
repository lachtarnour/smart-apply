import QtQuick
import QtQuick.Controls

ComboBox {
    id: root
    property int fontPixelSize: 13
    property int indicatorSize: 16
    property int indicatorMargin: 15
    property bool emphasized: false
    implicitHeight: Theme.controlHeight
    implicitWidth: 180
    hoverEnabled: true
    Accessible.name: displayText
    leftPadding: 15
    rightPadding: 42

    contentItem: Text {
        text: root.displayText
        color: Theme.ink
        font.pixelSize: root.fontPixelSize
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        renderType: Text.NativeRendering
    }

    indicator: SvgIcon {
        source: Theme.icon("chevron-right")
        color: root.visualFocus || root.emphasized ? Theme.accentBright : Theme.inkMuted
        width: root.indicatorSize; height: root.indicatorSize
        x: root.width - width - root.indicatorMargin
        y: (root.height - height) / 2
        rotation: root.popup.visible ? -90 : 90
        Behavior on rotation { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
    }

    background: Rectangle {
        radius: Theme.radiusMedium
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop {
                position: 0
                color: root.down ? Theme.surfacePressed : (root.hovered ? Theme.surfaceRaised : Theme.surfaceMuted)
                Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            }
            GradientStop {
                position: 1
                color: root.down ? Theme.surfacePressed : Theme.surface
                Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            }
        }
        border.color: root.activeFocus ? Theme.accent
            : root.hovered ? Theme.lineStrong
            : root.emphasized ? Theme.accentLine
            : Theme.line
        border.width: root.activeFocus ? Theme.lineWidthStrong : Theme.lineWidth
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
    }

    popup: Popup {
        y: root.height + 7
        width: root.width
        implicitHeight: Math.min(contentItem.implicitHeight + 12, 300)
        padding: 6
        background: Rectangle {
            radius: Theme.radiusMedium
            color: Theme.surface
            border.color: Theme.lineStrong
            Rectangle { anchors.fill: parent; anchors.topMargin: 3; anchors.bottomMargin: -3; z: -1; radius: Theme.radiusMedium; color: Theme.shadow }
        }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.delegateModel
            currentIndex: root.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator { }
        }
    }

    delegate: ItemDelegate {
        id: option
        required property int index
        width: root.width - 12
        height: 38
        highlighted: root.highlightedIndex === index
        contentItem: Text {
            text: root.textAt(index)
            color: option.highlighted ? Theme.accentDark : Theme.inkSoft
            font.pixelSize: root.fontPixelSize
            font.weight: option.highlighted ? Font.DemiBold : Font.Normal
            verticalAlignment: Text.AlignVCenter
            leftPadding: 7
            renderType: Text.NativeRendering
        }
        background: Rectangle { radius: 9; color: option.highlighted ? Theme.accentSoft : "transparent" }
    }
}

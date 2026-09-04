import QtQuick
import QtQuick.Controls

ComboBox {
    id: root
    implicitHeight: 48
    implicitWidth: 180
    hoverEnabled: true
    leftPadding: 15
    rightPadding: 42

    contentItem: Text {
        text: root.displayText
        color: Theme.ink
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: SvgIcon {
        source: Theme.icon("chevron-right")
        color: root.activeFocus ? Theme.accent : Theme.inkMuted
        width: 16; height: 16
        x: root.width - width - 15
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
        border.color: root.activeFocus ? Theme.accent : (root.hovered ? Theme.lineStrong : Theme.line)
        border.width: root.activeFocus ? 1.5 : 1
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
            font.pixelSize: 12
            font.weight: option.highlighted ? Font.DemiBold : Font.Normal
            verticalAlignment: Text.AlignVCenter
            leftPadding: 7
        }
        background: Rectangle { radius: 9; color: option.highlighted ? Theme.accentSoft : "transparent" }
    }
}

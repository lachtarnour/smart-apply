import QtQuick
import QtQuick.Controls

TextField {
    id: root
    property string iconText: ""
    property url iconSource

    implicitHeight: Theme.controlHeight
    color: Theme.ink
    placeholderTextColor: Theme.inkMuted
    selectionColor: "#6556B98A"
    selectedTextColor: Theme.ink
    font.pixelSize: Theme.bodySize
    leftPadding: (iconSource.toString().length > 0 || iconText.length > 0) ? 43 : 15
    rightPadding: 15
    selectByMouse: true
    Accessible.name: placeholderText

    background: Rectangle {
        radius: Theme.radiusMedium
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop {
                position: 0
                color: root.activeFocus ? Theme.surfaceRaised : Theme.surfaceMuted
                Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            }
            GradientStop {
                position: 1
                color: root.activeFocus ? Theme.surface : "#171620"
                Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            }
        }
        border.color: root.activeFocus ? Theme.accent : (fieldHover.hovered ? Theme.lineStrong : Theme.line)
        border.width: root.activeFocus ? Theme.lineWidthStrong : Theme.lineWidth
        Rectangle {
            visible: root.activeFocus
            anchors.fill: parent
            anchors.margins: -3
            radius: Theme.radiusMedium + 3
            color: "transparent"
            border.color: "#286E5BFF"
        }
        SvgIcon {
            visible: root.iconSource.toString().length > 0
            source: root.iconSource
            width: 17; height: 17
            color: root.activeFocus ? Theme.accent : Theme.inkMuted
            anchors.left: parent.left
            anchors.leftMargin: 15
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            visible: root.iconSource.toString().length === 0 && root.iconText.length > 0
            text: root.iconText
            color: root.activeFocus ? Theme.accent : Theme.inkMuted
            font.pixelSize: 15
            anchors.left: parent.left
            anchors.leftMargin: 15
            anchors.verticalCenter: parent.verticalCenter
        }
        HoverHandler { id: fieldHover }
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
    }
}

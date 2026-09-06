import QtQuick
import QtQuick.Controls

ScrollView {
    id: root
    property alias text: field.text
    property alias placeholderText: field.placeholderText
    property bool readOnly: false
    readonly property bool editing: field.activeFocus
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    property int fontPixelSize: 13
    clip: true
    ScrollBar.vertical: AppScrollBar { }
    background: Rectangle {
        radius: Theme.radiusMedium
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop {
                position: 0
                color: field.activeFocus ? Theme.surfaceRaised : (root.readOnly ? Theme.surface : Theme.surfaceMuted)
                Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            }
            GradientStop {
                position: 1
                color: field.activeFocus ? Theme.surface : "#171620"
                Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            }
        }
        border.color: field.activeFocus ? Theme.accent : (areaHover.hovered ? Theme.lineStrong : Theme.line)
        border.width: field.activeFocus ? Theme.lineWidthStrong : Theme.lineWidth
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
        Rectangle {
            visible: field.activeFocus
            anchors.fill: parent
            anchors.margins: -3
            radius: Theme.radiusMedium + 3
            color: "transparent"
            border.color: "#286E5BFF"
        }
        HoverHandler { id: areaHover }
    }
    TextArea {
        id: field
        readOnly: root.readOnly
        color: Theme.ink
        placeholderTextColor: Theme.inkMuted
        selectionColor: "#6556B98A"
        wrapMode: TextArea.Wrap
        font.pixelSize: root.fontPixelSize
        padding: 14
        rightPadding: 14 + Theme.scrollGutter
        selectByMouse: true
        Accessible.name: root.placeholderText
        background: null
    }
}

import QtQuick
import QtQuick.Controls

SpinBox {
    id: root
    implicitHeight: 48
    implicitWidth: 132
    editable: true
    leftPadding: 42
    rightPadding: 42

    contentItem: TextInput {
        z: 2
        text: root.textFromValue(root.value, root.locale)
        color: Theme.ink
        selectionColor: "#6556B98A"
        selectedTextColor: Theme.ink
        font.pixelSize: 13
        font.weight: Font.DemiBold
        horizontalAlignment: Qt.AlignHCenter
        verticalAlignment: Qt.AlignVCenter
        readOnly: !root.editable
        validator: root.validator
        inputMethodHints: Qt.ImhFormattedNumbersOnly
    }

    up.indicator: Rectangle {
        x: root.width - width - 5
        y: 5
        width: 34; height: root.height - 10
        radius: 9
        color: root.up.pressed ? Theme.surfacePressed : (upHover.hovered ? Theme.surfaceHover : "transparent")
        SvgIcon { anchors.centerIn: parent; source: Theme.icon("plus"); color: root.enabled ? Theme.inkSoft : Theme.inkFaint; width: 15; height: 15 }
        HoverHandler { id: upHover }
    }
    down.indicator: Rectangle {
        x: 5; y: 5
        width: 34; height: root.height - 10
        radius: 9
        color: root.down.pressed ? Theme.surfacePressed : (downHover.hovered ? Theme.surfaceHover : "transparent")
        SvgIcon { anchors.centerIn: parent; source: Theme.icon("minus"); color: root.enabled ? Theme.inkSoft : Theme.inkFaint; width: 15; height: 15 }
        HoverHandler { id: downHover }
    }
    background: Rectangle {
        radius: Theme.radiusMedium
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: Theme.surfaceMuted }
            GradientStop { position: 1; color: Theme.surface }
        }
        border.color: root.activeFocus ? Theme.accent : Theme.line
        border.width: root.activeFocus ? 1.5 : 1
        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 12; anchors.rightMargin: 12; anchors.top: parent.top; height: 1; color: Theme.highlight }
    }
}

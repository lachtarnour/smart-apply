import QtQuick

Item {
    id: root
    property bool checked: false
    property bool partial: false
    signal toggled(bool checked)

    implicitWidth: 28
    implicitHeight: 28
    opacity: enabled ? 1 : 0.45

    Rectangle {
        width: 18
        height: 18
        radius: 5
        anchors.centerIn: parent
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: root.checked || root.partial ? Theme.accentBright : Theme.surfaceRaised }
            GradientStop { position: 1; color: root.checked || root.partial ? Theme.accentDeep : Theme.surface }
        }
        border.color: root.checked || root.partial ? Theme.accent : (hover.hovered ? Theme.inkMuted : Theme.lineStrong)
        border.width: 1
        SvgIcon {
            anchors.centerIn: parent
            width: 11; height: 11
            source: root.partial && !root.checked ? Theme.icon("minus") : Theme.icon("check")
            color: "#FFFFFF"
            opacity: root.checked || root.partial ? 1 : 0
            scale: root.checked || root.partial ? 1 : 0.65
            Behavior on opacity { NumberAnimation { duration: 110 } }
            Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutBack } }
        }
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }
    HoverHandler { id: hover; enabled: root.enabled }
    TapHandler { enabled: root.enabled; onTapped: root.toggled(!root.checked) }
}

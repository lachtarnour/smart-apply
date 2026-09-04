import QtQuick
import QtQuick.Controls

ScrollBar {
    id: root
    policy: ScrollBar.AsNeeded
    interactive: true
    implicitWidth: 9
    minimumSize: 0.08

    contentItem: Rectangle {
        implicitWidth: 5
        radius: 3
        color: root.pressed ? Theme.accent : (root.hovered ? Theme.inkMuted : Theme.inkFaint)
        opacity: root.size < 1 ? (root.active ? 0.9 : 0.34) : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        Behavior on color { ColorAnimation { duration: 120 } }
    }

    background: Item { }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: root
    property string symbol: ""
    property url iconSource
    property bool selected: false
    property bool expanded: false
    property string compactText: text

    implicitWidth: expanded ? 184 : 62
    implicitHeight: expanded ? 48 : 58
    hoverEnabled: true
    padding: 0
    scale: down ? 0.985 : 1
    activeFocusOnTab: true
    Accessible.name: text
    Accessible.role: Accessible.Button

    contentItem: Item {
        RowLayout {
            visible: root.expanded
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 12
            spacing: 11

            SvgIcon {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                visible: root.iconSource.toString().length > 0
                source: root.iconSource
                color: root.selected ? Theme.accentBright : (root.hovered ? Theme.inkSoft : Theme.inkMuted)
            }
            Text {
                Layout.fillWidth: true
                text: root.text
                color: root.selected ? Theme.ink : (root.hovered ? Theme.inkSoft : Theme.inkMuted)
                font.pixelSize: 13
                font.weight: root.selected ? Font.DemiBold : Font.Medium
                elide: Text.ElideRight
            }
        }

        Column {
            visible: !root.expanded
            anchors.centerIn: parent
            spacing: 4
            SvgIcon {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: root.iconSource.toString().length > 0
                source: root.iconSource
                color: root.selected ? Theme.accentBright : (root.hovered ? Theme.inkSoft : Theme.inkFaint)
                width: 21; height: 21
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.max(50, root.width - 4)
                text: root.compactText
                color: root.selected ? Theme.ink : (root.hovered ? Theme.inkSoft : Theme.inkFaint)
                font.pixelSize: 10
                font.weight: root.selected ? Font.DemiBold : Font.Medium
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                renderType: Text.NativeRendering
            }
        }
    }

    background: Item {
        Rectangle {
            visible: root.selected
            anchors.fill: parent
            anchors.topMargin: 4
            anchors.bottomMargin: -4
            radius: root.expanded ? 13 : 16
            color: "#4A000000"
        }
        Rectangle {
            anchors.fill: parent
            radius: root.expanded ? 13 : 16
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop {
                    position: 0
                    color: root.selected ? "#3C315D" : (root.hovered ? Theme.surfaceMuted : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
                }
                GradientStop {
                    position: 1
                    color: root.selected ? "#2C2744" : (root.hovered ? "#17161E" : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
                }
            }
            border.color: root.visualFocus ? Theme.accentBright : root.selected ? Theme.accentLine : (root.hovered ? Theme.line : "transparent")
            border.width: Theme.lineWidth
            Behavior on border.color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            Rectangle {
                visible: root.selected
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                anchors.top: parent.top
                height: 1
                color: "#24FFFFFF"
            }
        }
        Rectangle {
            visible: root.selected
            width: 4
            height: root.expanded ? 20 : 22
            radius: 2
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.accentBright
            Rectangle { anchors.centerIn: parent; width: 7; height: parent.height + 8; radius: 4; color: "#307C65FF"; z: -1 }
        }
    }

    Behavior on scale { NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
}

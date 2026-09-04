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

    implicitWidth: expanded ? 184 : 58
    implicitHeight: expanded ? 46 : 56
    hoverEnabled: true
    padding: 0
    scale: down ? 0.975 : (hovered ? 1.008 : 1)

    ToolTip.visible: hovered && !expanded
    ToolTip.text: text
    ToolTip.delay: 500

    contentItem: Item {
        RowLayout {
            visible: root.expanded
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 12
            spacing: 11

            SvgIcon {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                visible: root.iconSource.toString().length > 0
                source: root.iconSource
                color: root.selected ? Theme.accentBright : (root.hovered ? Theme.inkSoft : Theme.inkMuted)
            }
            Text {
                Layout.fillWidth: true
                text: root.text
                color: root.selected ? Theme.ink : (root.hovered ? Theme.inkSoft : Theme.inkMuted)
                font.pixelSize: 12
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
                width: 19; height: 19
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.max(48, root.width - 4)
                text: root.compactText
                color: root.selected ? Theme.ink : (root.hovered ? Theme.inkSoft : Theme.inkFaint)
                font.pixelSize: 9
                font.weight: root.selected ? Font.DemiBold : Font.Medium
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
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
                    color: root.selected ? "#312947" : (root.hovered ? Theme.surfaceMuted : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
                }
                GradientStop {
                    position: 1
                    color: root.selected ? "#24212F" : (root.hovered ? "#17161E" : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
                }
            }
            border.color: root.selected ? Theme.accentLine : (root.hovered ? Theme.line : "transparent")
            border.width: 1
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
            width: 3
            height: root.expanded ? 18 : 20
            radius: 2
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.accentBright
            Rectangle { anchors.centerIn: parent; width: 7; height: parent.height + 8; radius: 4; color: "#307C65FF"; z: -1 }
        }
    }

    Behavior on scale { NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
}

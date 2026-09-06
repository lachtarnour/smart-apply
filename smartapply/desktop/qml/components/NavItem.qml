import QtQuick
import QtQuick.Controls

Button {
    id: root
    property string iconText: ""
    property bool selected: false

    implicitHeight: 48
    hoverEnabled: true
    leftPadding: 14
    rightPadding: 12

    contentItem: Row {
        spacing: 13
        Text {
            width: 23
            text: root.iconText
            color: root.selected ? "#FFFFFF" : (root.hovered ? "#D9D5FF" : "#8990A8")
            font.pixelSize: 19
            font.weight: Font.Medium
            horizontalAlignment: Text.AlignHCenter
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.text
            color: root.selected ? "#FFFFFF" : (root.hovered ? "#FFFFFF" : "#AEB3C5")
            font.pixelSize: 14
            font.weight: root.selected ? Font.DemiBold : Font.Medium
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    background: Rectangle {
        radius: 13
        color: root.selected ? "#29263D" : (root.hovered ? "#211F31" : "transparent")
        border.color: root.selected ? "#3C3857" : "transparent"
        border.width: Theme.lineWidth
        Rectangle {
            visible: root.selected
            width: 3
            height: 22
            radius: 2
            color: "#8E82FF"
            anchors.left: parent.left
            anchors.leftMargin: 1
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}

import QtQuick
import QtQuick.Controls

Button {
    id: root
    property string title: ""
    property string sortKey: ""
    property bool active: false
    property bool ascending: true
    property bool alignRight: false
    signal sortRequested(string key)

    implicitHeight: 38
    hoverEnabled: true
    padding: 0
    onClicked: sortRequested(sortKey)

    contentItem: Row {
        spacing: 4
        anchors.left: root.alignRight ? undefined : parent.left
        anchors.right: root.alignRight ? parent.right : undefined
        anchors.verticalCenter: parent.verticalCenter
        Text {
            text: root.title.toUpperCase()
            color: root.active ? Theme.ink : Theme.inkMuted
            font.pixelSize: 9
            font.weight: Font.Bold
            font.letterSpacing: 0.55
            anchors.verticalCenter: parent.verticalCenter
        }
        SvgIcon {
            visible: root.active
            source: Theme.icon("chevron-right")
            color: Theme.accent
            width: 11; height: 11
            rotation: root.ascending ? -90 : 90
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Rectangle {
        radius: 8
        color: root.hovered ? Theme.surfaceHover : "transparent"
    }
}

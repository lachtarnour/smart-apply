import QtQuick
import QtQuick.Controls

Button {
    id: root
    property string title: ""
    property string sortKey: ""
    property bool active: false
    property bool ascending: true
    property bool centered: false
    signal sortRequested(string key)

    implicitHeight: 38
    hoverEnabled: true
    clip: true
    padding: 0
    leftPadding: 0
    rightPadding: 0
    onClicked: sortRequested(sortKey)

    Accessible.name: "Trier par " + title
    contentItem: Item {
        Row {
            spacing: 3
            x: root.centered ? Math.max(0, (parent.width - width) / 2) : 0
            anchors.verticalCenter: parent.verticalCenter
            Text {
                text: root.title
                color: root.active ? Theme.inkSoft : Theme.inkMuted
                font.pixelSize: 10
                font.weight: Font.Medium
                anchors.verticalCenter: parent.verticalCenter
                renderType: Text.NativeRendering
            }
            SvgIcon {
                visible: root.active
                source: Theme.icon("chevron-right")
                color: Theme.accentBright
                width: 9; height: 9
                rotation: root.ascending ? -90 : 90
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
    background: Rectangle {
        radius: 6
        color: root.hovered || root.visualFocus ? Theme.surfaceHover : "transparent"
    }
}

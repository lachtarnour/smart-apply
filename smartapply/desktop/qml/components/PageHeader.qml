import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property string eyebrow: ""
    property string title: ""
    property string subtitle: ""
    default property alias actions: actionsRow.data
    readonly property bool hasSupportingText: eyebrow.length > 0 || subtitle.length > 0
    implicitHeight: hasSupportingText ? 100 : 80

    ColumnLayout {
        anchors.left: parent.left
        anchors.right: actionsRow.left
        anchors.rightMargin: actionsRow.children.length > 0 ? 24 : 0
        anchors.verticalCenter: parent.verticalCenter
        spacing: 5
        Text {
            visible: root.eyebrow.length > 0
            text: root.eyebrow
            color: Theme.accent
            font.family: Theme.fontFamily
            font.pixelSize: 10
            font.weight: Font.Bold
            font.letterSpacing: 1.45
        }
        MetallicTitle {
            Layout.fillWidth: true
            text: root.title
            pixelSize: 32
            letterSpacing: -1.05
        }
        Text {
            visible: root.subtitle.length > 0
            text: root.subtitle
            color: Theme.inkMuted
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.Medium
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Layout.maximumWidth: 760
        }
    }
    RowLayout {
        id: actionsRow
        anchors.right: parent.right
        anchors.rightMargin: 2
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10
    }
}

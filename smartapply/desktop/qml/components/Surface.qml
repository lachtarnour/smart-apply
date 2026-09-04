import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property alias content: body.data
    property int padding: 22
    property color surfaceColor: Theme.surface
    property color surfaceEndColor: surfaceColor
    property color strokeColor: Theme.line
    property int radiusValue: Theme.radiusLarge
    property bool elevated: true
    property bool luminous: false
    default property alias contentData: body.data

    implicitHeight: body.implicitHeight + padding * 2

    Rectangle {
        visible: root.elevated
        anchors.fill: parent
        anchors.leftMargin: 1
        anchors.rightMargin: -1
        anchors.topMargin: 8
        anchors.bottomMargin: -8
        radius: root.radiusValue + 4
        color: Theme.shadow
    }
    Rectangle {
        visible: root.elevated && root.luminous
        anchors.fill: parent
        anchors.margins: -2
        radius: root.radiusValue + 3
        color: "transparent"
        border.color: "#245F4BFF"
        border.width: 1
    }
    Rectangle {
        anchors.fill: parent
        radius: root.radiusValue
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: root.surfaceColor }
            GradientStop { position: 1; color: root.surfaceEndColor }
        }
        border.color: root.strokeColor
        border.width: 1

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: root.radiusValue
            anchors.rightMargin: root.radiusValue
            anchors.top: parent.top
            height: 1
            color: Theme.highlight
        }
    }

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: root.padding
        spacing: 16
    }
}

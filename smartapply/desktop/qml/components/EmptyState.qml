import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string symbol: "✦"
    property url iconSource: Theme.icon("sparkle")
    property string title: ""
    property string message: ""
    spacing: 10
    width: parent ? Math.max(0, Math.min(360, parent.width - 32)) : 320
    implicitWidth: 320
    Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
    Item {
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: 66; Layout.preferredHeight: 66
        Rectangle {
            anchors.centerIn: parent
            width: 64; height: 64; radius: 22
            color: "#1C765FFF"
            opacity: 0.72
        }
        Rectangle {
            anchors.centerIn: parent
            width: 54; height: 54; radius: 18
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0; color: "#39305A" }
                GradientStop { position: 1; color: Theme.accentSoft }
            }
            border.color: Theme.accentLine
            SvgIcon { anchors.centerIn: parent; source: root.iconSource; color: Theme.accentBright; width: 23; height: 23 }
            Text {
                visible: root.iconSource.toString().length === 0
                anchors.centerIn: parent
                text: root.symbol
                color: Theme.accentBright
                font.pixelSize: 24
            }
        }
    }
    Text {
        id: titleLabel
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        text: root.title
        color: Theme.ink
        font.pixelSize: 17
        font.weight: Font.Bold
        font.letterSpacing: -0.2
    }
    Text {
        id: messageLabel
        visible: root.message.length > 0
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
        Layout.maximumWidth: 360
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        text: root.message
        color: Theme.inkMuted
        font.pixelSize: 13
        lineHeight: 1.25
    }
}

import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root
    property string title: ""
    default property alias actions: actionsRow.data
    spacing: 24

    Text {
        Layout.fillWidth: true
        text: root.title
        color: Theme.ink
        font.family: Theme.fontFamily
        font.pixelSize: Theme.pageTitleSize
        font.weight: Font.Bold
        font.letterSpacing: -0.5
        wrapMode: Text.WordWrap
    }
    RowLayout {
        id: actionsRow
        Layout.alignment: Qt.AlignVCenter
        spacing: 8
    }
}

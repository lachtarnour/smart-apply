import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root
    property string title: ""
    property string caption: ""
    default property alias actions: actionArea.data
    Layout.fillWidth: true
    spacing: 12

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 3
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: root.title
            color: Theme.ink
            font.family: Theme.fontFamily
            font.pixelSize: Theme.sectionTitleSize
            font.weight: Font.Bold
            font.letterSpacing: -0.35
            renderType: Text.NativeRendering
        }
        Text {
            visible: root.caption.length > 0
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: root.caption
            color: Theme.inkMuted
            font.pixelSize: 12
            font.weight: Font.Medium
            renderType: Text.NativeRendering
        }
    }
    RowLayout { id: actionArea; spacing: 8 }
}

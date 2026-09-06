import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

CheckBox {
    id: root
    property string symbol: ""
    implicitHeight: Theme.controlHeight
    implicitWidth: contentRow.implicitWidth + 28
    leftPadding: 14
    rightPadding: 14
    hoverEnabled: true
    opacity: enabled ? 1 : 0.45
    indicator: Item { width: 0; height: 0 }
    contentItem: RowLayout {
        id: contentRow
        spacing: 10
        Text {
            visible: root.symbol.length > 0
            Layout.preferredWidth: 20
            text: root.symbol
            color: root.checked ? Theme.accentBright : Theme.inkMuted
            font.pixelSize: 13
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
        }
        Text {
            Layout.fillWidth: true
            text: root.text
            color: root.checked ? Theme.accentBright : Theme.inkSoft
            font.pixelSize: 13
            font.weight: Font.Medium
            elide: Text.ElideRight
        }
        Rectangle {
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            radius: 5
            color: root.checked ? Theme.accent : "transparent"
            border.color: root.checked ? Theme.accent : Theme.lineStrong
            SvgIcon { anchors.centerIn: parent; width: 11; height: 11; source: Theme.icon("check"); visible: root.checked; color: "white" }
        }
    }
    background: Rectangle {
        radius: Theme.radiusMedium
        color: root.checked ? Theme.accentSoft : (root.hovered ? Theme.surfaceHover : Theme.surfaceMuted)
        border.color: root.visualFocus ? Theme.accent : (root.checked ? Theme.accentLine : Theme.line)
        border.width: root.visualFocus ? 2 : 1
        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }
    }
}

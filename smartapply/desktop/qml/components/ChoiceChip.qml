import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

CheckBox {
    id: root
    property string symbol: ""
    implicitHeight: 40
    implicitWidth: contentRow.implicitWidth + 28
    hoverEnabled: true
    spacing: 0
    indicator: Item { width: 0; height: 0 }
    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: Math.max(16, contentRow.implicitHeight)

        RowLayout {
            id: contentRow
            anchors.centerIn: parent
            spacing: 8
            Text {
                visible: root.symbol.length > 0
                text: root.symbol
                Layout.alignment: Qt.AlignVCenter
                color: root.checked ? Theme.accentDark : Theme.inkMuted
                font.family: Theme.fontFamily
                font.pixelSize: 14
                verticalAlignment: Text.AlignVCenter
            }
            Text {
                text: root.text
                Layout.alignment: Qt.AlignVCenter
                color: root.checked ? Theme.accentDark : Theme.inkSoft
                font.family: Theme.fontFamily
                font.pixelSize: 12
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
            }
            Rectangle {
                Layout.preferredWidth: 16
                Layout.preferredHeight: 16
                Layout.alignment: Qt.AlignVCenter
                radius: 5
                color: root.checked ? Theme.accent : "transparent"
                border.color: root.checked ? Theme.accent : Theme.lineStrong
                SvgIcon {
                    anchors.centerIn: parent
                    width: 11; height: 11
                    source: Theme.icon("check")
                    opacity: root.checked ? 1 : 0
                    scale: root.checked ? 1 : 0.7
                    color: "white"
                    Behavior on opacity { NumberAnimation { duration: 120 } }
                    Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutBack } }
                }
                Behavior on color { ColorAnimation { duration: 130 } }
                Behavior on border.color { ColorAnimation { duration: 130 } }
            }
        }
    }
    background: Rectangle {
        radius: 11
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop {
                position: 0
                color: root.checked ? "#3A3060" : (root.hovered ? Theme.surfaceRaised : Theme.surfaceMuted)
                Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            }
            GradientStop {
                position: 1
                color: root.checked ? Theme.accentSoft : Theme.surface
                Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            }
        }
        border.color: root.activeFocus ? Theme.accent : (root.checked ? Theme.accentLine : (root.hovered ? Theme.lineStrong : Theme.line))
        border.width: root.activeFocus ? 1.5 : 1
        opacity: root.enabled ? 1 : 0.45
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
    }
}

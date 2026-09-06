import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: root
    property url iconSource
    property string title: ""
    property string caption: ""
    property string badge: ""
    property color accent: Theme.accent

    implicitHeight: root.caption.length > 0 ? 68 : 62
    hoverEnabled: true
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: root.title
    padding: 0
    scale: down ? 0.98 : (hovered ? 1.008 : 1)

    contentItem: RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 12

        Rectangle {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            radius: 13
            color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, root.hovered ? 0.16 : 0.1)
            border.color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, root.hovered ? 0.26 : 0.14)
            SvgIcon { anchors.centerIn: parent; source: root.iconSource; color: root.accent; width: 19; height: 19 }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                visible: root.caption.length > 0
                Layout.fillWidth: true
                text: root.title
                color: Theme.ink
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                renderType: Text.NativeRendering
            }
            Text {
                Layout.fillWidth: true
                text: root.caption
                color: Theme.inkMuted
                font.pixelSize: 11
                elide: Text.ElideRight
                renderType: Text.NativeRendering
            }
        }

        Rectangle {
            visible: root.badge.length > 0
            Layout.preferredWidth: Math.max(28, badgeText.implicitWidth + 14)
            Layout.preferredHeight: 24
            radius: 8
            color: root.hovered ? Theme.accentSoft : Theme.neutralSoft
            Text { id: badgeText; anchors.centerIn: parent; text: root.badge; color: root.hovered ? Theme.accentDark : Theme.inkMuted; font.pixelSize: 10; font.weight: Font.DemiBold; renderType: Text.NativeRendering }
        }
        SvgIcon { source: Theme.icon("chevron-right"); color: root.hovered ? Theme.accent : Theme.inkFaint; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
    }

    background: Rectangle {
        radius: 14
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: root.down ? Theme.surfacePressed : (root.hovered ? Theme.surfaceRaised : Theme.surfaceMuted) }
            GradientStop { position: 1; color: root.down ? Theme.surfacePressed : Theme.surface }
        }
        border.color: root.activeFocus ? Theme.accent : (root.hovered ? Theme.accentLine : Theme.line)
        border.width: root.activeFocus ? Theme.lineWidthStrong : Theme.lineWidth
        Behavior on border.color { ColorAnimation { duration: 130 } }
        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 14; anchors.rightMargin: 14; anchors.top: parent.top; height: Theme.lineWidth; color: Theme.highlight }
    }

    Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
}

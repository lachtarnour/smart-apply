import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: root
    property string kind: "secondary"
    property string iconText: ""
    property url iconSource
    property int iconSize: 17
    property color accentColor: Theme.accent

    implicitHeight: 44
    implicitWidth: Math.max(96, contentItem.implicitWidth + 34)
    hoverEnabled: true
    leftPadding: 17
    rightPadding: 17
    topPadding: 0
    bottomPadding: 0
    scale: down ? 0.972 : (hovered && enabled ? 1.012 : 1)
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text

    contentItem: Item {
        implicitWidth: buttonContent.implicitWidth
        implicitHeight: Math.max(root.iconSize, buttonLabel.implicitHeight)

        RowLayout {
            id: buttonContent
            anchors.centerIn: parent
            spacing: 7
            transform: Translate {
                y: root.down ? 1 : 0
                Behavior on y { NumberAnimation { duration: Theme.motionQuick; easing.type: Easing.OutCubic } }
            }
            SvgIcon {
                visible: root.iconSource.toString().length > 0
                source: root.iconSource
                Layout.preferredWidth: root.iconSize
                Layout.preferredHeight: root.iconSize
                Layout.alignment: Qt.AlignVCenter
                color: !root.enabled ? Theme.inkFaint : (root.kind === "primary" ? "#FFFFFF" : (root.kind === "danger" ? Theme.danger : Theme.inkSoft))
            }
            Text {
                visible: root.iconSource.toString().length === 0 && root.iconText.length > 0
                text: root.iconText
                Layout.alignment: Qt.AlignVCenter
                color: !root.enabled ? Theme.inkFaint : (root.kind === "primary" ? "white" : (root.kind === "danger" ? Theme.danger : Theme.inkSoft))
                font.family: Theme.fontFamily
                font.pixelSize: 15
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
            }
            Text {
                id: buttonLabel
                text: root.text
                Layout.alignment: Qt.AlignVCenter
                color: !root.enabled ? Theme.inkFaint : (root.kind === "primary" ? "white" : (root.kind === "danger" ? Theme.danger : Theme.ink))
                font.family: Theme.fontFamily
                font.pixelSize: 12
                font.weight: Font.DemiBold
                font.letterSpacing: 0.05
                verticalAlignment: Text.AlignVCenter
                renderType: Text.NativeRendering
            }
        }
    }

    background: Item {
        Rectangle {
            visible: root.kind === "primary" && root.enabled
            anchors.fill: parent
            anchors.leftMargin: 2
            anchors.rightMargin: -2
            anchors.topMargin: 6
            anchors.bottomMargin: -6
            radius: Theme.radiusMedium + 2
            color: root.hovered ? "#6A000000" : "#52000000"
        }
        Rectangle {
            visible: root.kind === "primary" && root.enabled && root.hovered
            anchors.fill: parent
            anchors.margins: -2
            radius: Theme.radiusMedium + 2
            color: "transparent"
            border.color: "#427F6BFF"
        }
        Rectangle {
            anchors.fill: parent
            radius: Theme.radiusMedium
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop {
                    position: 0
                    color: !root.enabled ? Theme.neutralSoft
                         : root.kind === "primary" ? (root.down ? "#7566EA" : (root.hovered ? "#A194FF" : root.accentColor))
                         : root.kind === "danger" ? (root.hovered ? "#4B2732" : Theme.dangerSoft)
                         : (root.down ? Theme.surfacePressed : (root.hovered ? Theme.surfaceRaised : Theme.surfaceMuted))
                    Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
                }
                GradientStop {
                    position: 1
                    color: !root.enabled ? Theme.neutralSoft
                         : root.kind === "primary" ? (root.down ? "#5F50D1" : (root.hovered ? "#7D6DF2" : Theme.accentDeep))
                         : root.kind === "danger" ? Theme.dangerSoft
                         : (root.down ? Theme.surfacePressed : Theme.surface)
                    Behavior on color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
                }
            }
            border.color: root.activeFocus ? Theme.accent
                          : root.kind === "primary" ? (root.enabled ? root.accentColor : Theme.line)
                          : root.kind === "danger" ? "#60313B" : (root.hovered ? Theme.lineStrong : Theme.line)
            border.width: root.activeFocus ? 1.5 : 1
            Behavior on border.color { ColorAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: Theme.radiusMedium
                anchors.rightMargin: Theme.radiusMedium
                anchors.top: parent.top
                height: 1
                color: root.kind === "primary" ? "#42FFFFFF" : Theme.highlight
            }
        }
    }

    Behavior on scale { NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic } }
}

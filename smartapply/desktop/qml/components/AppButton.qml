import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: root
    property string kind: "secondary"
    property string iconText: ""
    property url iconSource
    property bool refined: false
    property bool quiet: false
    property int iconSize: refined ? 14 : 16
    property int fontPixelSize: 12
    property color accentColor: Theme.accent
    readonly property bool iconOnly: text.length === 0

    implicitHeight: Theme.controlHeight
    implicitWidth: iconOnly ? implicitHeight : Math.max(88, contentItem.implicitWidth + 28)
    hoverEnabled: true
    leftPadding: iconOnly ? 0 : 14
    rightPadding: iconOnly ? 0 : 14
    topPadding: 0
    bottomPadding: 0
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    scale: down && enabled ? 0.985 : 1

    function foregroundColor() {
        if (!enabled) return Theme.inkFaint
        if (kind === "primary") return refined || quiet ? Theme.accentBright : "#FFFFFF"
        if (kind === "success") return Theme.success
        if (kind === "warning") return Theme.warning
        if (kind === "danger") return Theme.danger
        return quiet && !hovered ? Theme.inkMuted : Theme.inkSoft
    }
    function fillColor() {
        if (!enabled) return Theme.surfaceMuted
        if (kind === "primary")
            return refined || quiet ? (hovered ? "#342B50" : "#252036") : (hovered ? "#9A89FF" : accentColor)
        if (kind === "success") return hovered ? "#1E473B" : "#17372E"
        if (kind === "warning") return hovered ? "#42321E" : "#302417"
        if (kind === "danger") return hovered ? "#44232E" : "#301D25"
        return down ? Theme.surfacePressed : hovered ? Theme.surfaceRaised : Theme.surfaceMuted
    }
    function strokeColor() {
        if (visualFocus) return Theme.accentBright
        if (!enabled) return Theme.line
        if (kind === "primary") return refined || quiet ? Theme.accentLine : Theme.accent
        if (kind === "success") return Theme.successLine
        if (kind === "warning") return Theme.warningLine
        if (kind === "danger") return Theme.dangerLine
        return hovered ? Theme.lineStrong : Theme.line
    }
    contentItem: Item {
        implicitWidth: buttonContent.implicitWidth
        implicitHeight: Math.max(root.iconSize, buttonLabel.implicitHeight)
        RowLayout {
            id: buttonContent
            anchors.centerIn: parent
            spacing: root.iconOnly ? 0 : 7
            SvgIcon {
                visible: root.iconSource.toString().length > 0
                source: root.iconSource
                Layout.preferredWidth: root.iconSize
                Layout.preferredHeight: root.iconSize
                color: root.foregroundColor()
            }
            Text {
                visible: root.iconSource.toString().length === 0 && root.iconText.length > 0
                text: root.iconText
                color: root.foregroundColor()
                font.pixelSize: root.iconSize
            }
            Text {
                id: buttonLabel
                visible: !root.iconOnly
                text: root.text
                color: root.foregroundColor()
                font.family: Theme.fontFamily
                font.pixelSize: root.fontPixelSize
                font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
    background: Rectangle {
        radius: root.refined ? 9 : Theme.radiusMedium
        color: root.fillColor()
        border.color: root.strokeColor()
        border.width: root.visualFocus ? 2 : 1
        opacity: root.quiet && !root.hovered && !root.down && !root.visualFocus ? 0 : 1
        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }
        Behavior on opacity { NumberAnimation { duration: Theme.motionFast } }
    }
    Behavior on scale { NumberAnimation { duration: Theme.motionQuick } }
}

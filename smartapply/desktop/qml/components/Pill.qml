import QtQuick

Rectangle {
    id: root
    property string text: ""
    property string tone: "neutral"
    property bool compact: false
    property int fontPixelSize: compact ? 11 : 12

    implicitWidth: label.implicitWidth + (compact ? 16 : 22)
    implicitHeight: compact ? Math.max(26, label.implicitHeight + 10) : Math.max(30, label.implicitHeight + 12)
    radius: 8
    gradient: Gradient {
        orientation: Gradient.Vertical
        GradientStop {
            position: 0
            color: root.tone === "success" ? "#21483C"
                 : root.tone === "warning" ? "#473621"
                 : root.tone === "danger" ? "#4C2934"
                 : root.tone === "accent" ? "#392F60" : "#2B2834"
        }
        GradientStop {
            position: 1
            color: root.tone === "success" ? Theme.successSoft
                 : root.tone === "warning" ? Theme.warningSoft
                 : root.tone === "danger" ? Theme.dangerSoft
                 : root.tone === "accent" ? Theme.accentSoft : Theme.neutralSoft
        }
    }
    border.color: tone === "success" ? "#285B4D"
                  : tone === "warning" ? "#594326"
                  : tone === "danger" ? "#60313B"
                  : tone === "accent" ? Theme.accentLine : Theme.lineStrong
    border.width: Theme.lineWidth

    Text {
        id: label
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        text: root.text
        color: root.tone === "success" ? Theme.success
               : root.tone === "warning" ? Theme.warning
               : root.tone === "danger" ? Theme.danger
               : root.tone === "accent" ? Theme.accentDark : Theme.inkSoft
        font.pixelSize: root.fontPixelSize
        font.weight: Font.DemiBold
        renderType: Text.NativeRendering
    }
}

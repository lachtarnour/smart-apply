import QtQuick

Rectangle {
    id: root
    property string text: ""
    property string tone: "neutral"
    property bool compact: false

    implicitWidth: label.implicitWidth + (compact ? 16 : 22)
    implicitHeight: compact ? 26 : 30
    radius: height / 2
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
    border.width: 1

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.tone === "success" ? Theme.success
               : root.tone === "warning" ? Theme.warning
               : root.tone === "danger" ? Theme.danger
               : root.tone === "accent" ? Theme.accentDark : Theme.inkSoft
        font.pixelSize: root.compact ? 11 : 12
        font.weight: Font.DemiBold
    }
}

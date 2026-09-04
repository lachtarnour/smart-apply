import QtQuick
import QtQuick.Layouts

Item {
    id: root
    property string label: ""
    property string value: "0"
    property string caption: ""
    property color accent: "#6558F5"
    property string symbol: "↗"
    property url iconSource
    property real progress: 0
    property string actionText: ""
    property bool interactive: false
    signal activated()

    implicitHeight: 142
    activeFocusOnTab: interactive
    Accessible.ignored: !interactive
    Accessible.role: Accessible.Button
    Accessible.name: root.label + " : " + root.value
    scale: cardTap.pressed ? 0.99 : (mouse.hovered && root.interactive ? 1.008 : 1)
    transform: Translate {
        y: mouse.hovered && root.interactive ? -2 : 0
        Behavior on y { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }
    }

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: 1
        anchors.rightMargin: -1
        anchors.topMargin: 8
        anchors.bottomMargin: -8
        radius: Theme.radiusLarge + 4
        color: Theme.shadow
    }
    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusLarge
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: mouse.hovered && root.interactive ? Theme.surfaceRaised : "#1A1823" }
            GradientStop { position: 1; color: mouse.hovered && root.interactive ? Theme.surfaceHover : Theme.surface }
        }
        border.color: root.activeFocus ? root.accent : (mouse.hovered && root.interactive ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.34) : Theme.line)
        border.width: root.activeFocus ? 1.5 : 1
        Behavior on border.color { ColorAnimation { duration: 140 } }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: Theme.radiusLarge
            anchors.rightMargin: Theme.radiusLarge
            anchors.top: parent.top
            height: 1
            color: Theme.highlight
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 4
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: root.label.toUpperCase()
                color: Theme.inkMuted
                font.pixelSize: 10
                font.letterSpacing: 0.7
                font.weight: Font.DemiBold
            }
            Item { Layout.fillWidth: true }
            Text {
                visible: root.interactive && root.actionText.length > 0
                text: root.actionText
                color: mouse.hovered ? root.accent : Theme.inkFaint
                font.pixelSize: 9
                font.weight: Font.DemiBold
            }
            Rectangle {
                Layout.preferredWidth: 32; Layout.preferredHeight: 32; radius: 11
                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop { position: 0; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.22) }
                    GradientStop { position: 1; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.08) }
                }
                border.color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.20)
                SvgIcon { anchors.centerIn: parent; visible: root.iconSource.toString().length > 0; source: root.iconSource; color: root.accent; width: 15; height: 15 }
                Text {
                    visible: root.iconSource.toString().length === 0
                    anchors.centerIn: parent
                    text: root.symbol
                    color: root.accent
                    font.pixelSize: 14
                    font.weight: Font.Bold
                }
            }
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Text { text: root.value; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: 32; font.weight: Font.Bold; font.letterSpacing: -0.6; renderType: Text.NativeRendering }
                Text { visible: root.caption.length > 0; text: root.caption; color: Theme.inkMuted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
            }
            SvgIcon {
                visible: root.interactive
                source: Theme.icon("chevron-right")
                color: mouse.hovered ? root.accent : Theme.inkFaint
                Layout.preferredWidth: 15
                Layout.preferredHeight: 15
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 3; radius: 2; color: "#272331"
            Rectangle {
                width: root.progress <= 0 ? 0 : Math.max(8, parent.width * Math.min(1, root.progress))
                height: 3
                radius: 2
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: root.accent }
                    GradientStop { position: 1; color: Theme.accentBright }
                }
                Behavior on width { NumberAnimation { duration: 480; easing.type: Easing.OutCubic } }
            }
        }
    }

    HoverHandler { id: mouse; cursorShape: root.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor }
    TapHandler { id: cardTap; enabled: root.interactive; onTapped: root.activated() }
    Keys.onReturnPressed: if (root.interactive) root.activated()
    Keys.onEnterPressed: if (root.interactive) root.activated()
    Keys.onSpacePressed: if (root.interactive) root.activated()
    Accessible.onPressAction: if (root.interactive) root.activated()
    Behavior on scale { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }
}

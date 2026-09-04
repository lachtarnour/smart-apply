import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    objectName: "confirmDialog"
    property string heading: "Confirmer l’action"
    property string message: ""
    property string confirmText: "Confirmer"
    property string kind: "primary"
    property url iconSource: Theme.icon(kind === "danger" ? "alert-circle" : "check")

    width: 430
    height: 244
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    background: Item {
        Rectangle {
            anchors.fill: parent
            anchors.topMargin: 12
            anchors.bottomMargin: -12
            radius: 26
            color: Theme.shadow
        }
        Rectangle {
            anchors.fill: parent
            radius: 24
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0; color: Theme.surfaceRaised }
                GradientStop { position: 1; color: Theme.surface }
            }
            border.color: root.kind === "danger" ? "#6B3946" : Theme.accentLine
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 22; anchors.rightMargin: 22; anchors.top: parent.top; height: 1; color: "#2BFFFFFF" }
        }
    }

    Overlay.modal: Rectangle { color: Theme.scrim }

    contentItem: ColumnLayout {
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 86
            Rectangle {
                width: 42; height: 42; radius: 13
                x: 22; anchors.verticalCenter: parent.verticalCenter
                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop { position: 0; color: root.kind === "danger" ? "#552D3A" : "#3B3160" }
                    GradientStop { position: 1; color: root.kind === "danger" ? Theme.dangerSoft : Theme.accentSoft }
                }
                border.color: root.kind === "danger" ? "#6B3946" : Theme.accentLine
                SvgIcon {
                    anchors.centerIn: parent
                    source: root.iconSource
                    color: root.kind === "danger" ? Theme.danger : Theme.accentDark
                    width: 19; height: 19
                }
            }
            Column {
                x: 78
                width: parent.width - 100
                anchors.verticalCenter: parent.verticalCenter
                spacing: 0
                Text { width: parent.width; text: root.heading; color: Theme.ink; font.pixelSize: 18; font.weight: Font.Bold; font.letterSpacing: -0.25; wrapMode: Text.WordWrap }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Text {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 22
                text: root.message
                color: Theme.inkSoft
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                lineHeight: 1.25
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 67
            color: Theme.surfaceMuted
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 1; color: Theme.line }
            RowLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 9
                Item { Layout.fillWidth: true }
                AppButton { text: "Annuler"; onClicked: root.reject() }
                AppButton { text: root.confirmText; kind: root.kind; onClicked: root.accept() }
            }
        }
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 150; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: 180; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 110 }
            NumberAnimation { property: "scale"; from: 1; to: 0.985; duration: 110 }
        }
    }
}

import QtQuick
import QtQuick.Controls

Item {
    id: root
    property string text: ""
    property string emptyText: "Contenu indisponible"

    clip: true

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusMedium
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: "#0D0C13" }
            GradientStop { position: 1; color: Theme.canvas }
        }
        border.color: Theme.line
    }

    Flickable {
        id: viewport
        anchors.fill: parent
        anchors.margins: 1
        contentWidth: width
        contentHeight: Math.max(height, paper.height + 22)
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollBar.vertical: AppScrollBar { }

        Rectangle {
            id: paper
            x: 11
            y: 11
            width: viewport.width - 31
            height: Math.max(viewport.height - 22, documentText.implicitHeight + 46)
            radius: 9
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0; color: Theme.surfaceRaised }
                GradientStop { position: 1; color: Theme.surface }
            }
            border.color: Theme.lineStrong

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 4
                radius: 2
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.accentDeep }
                    GradientStop { position: 0.55; color: Theme.accentBright }
                    GradientStop { position: 1; color: Theme.accent }
                }
            }

            Text {
                id: documentText
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 22
                anchors.topMargin: 25
                text: root.text.length > 0 ? root.text : root.emptyText
                color: Theme.inkSoft
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                lineHeight: 1.32
                textFormat: Text.PlainText
            }
        }
    }
}

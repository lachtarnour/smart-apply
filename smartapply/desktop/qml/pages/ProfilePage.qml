import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    signal navigateRequested(string route)

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight + 56
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: AppScrollBar { }
        ColumnLayout {
            id: content
            width: parent.width - 12
            spacing: 18
            PageHeader {
                Layout.fillWidth: true
                title: "Profil"
                AppButton { text: "Dossier du profil"; iconSource: Theme.icon("folder"); onClicked: AppBridge.openProfileFolder() }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 225
                radius: 26
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "#181520" }
                    GradientStop { position: 0.58; color: "#201A30" }
                    GradientStop { position: 1; color: "#30264A" }
                }
                border.color: "#4B435E"
                clip: true
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 26; anchors.rightMargin: 26; anchors.top: parent.top; height: 1; color: "#30FFFFFF" }
                Rectangle { width: 320; height: 320; radius: 160; x: parent.width - 190; y: -135; color: "#28735CFF" }
                Rectangle { width: 150; height: 150; radius: 75; x: parent.width - 370; y: 155; color: "#1B9079FF" }
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 28
                    spacing: 22
                    Rectangle {
                        Layout.preferredWidth: 88; Layout.preferredHeight: 88; radius: 28
                        gradient: Gradient {
                            GradientStop { position: 0; color: Theme.accentBright }
                            GradientStop { position: 0.48; color: Theme.accent }
                            GradientStop { position: 1; color: Theme.accentDeep }
                        }
                        border.color: "#5AFFFFFF"
                        Rectangle { anchors.fill: parent; anchors.margins: -4; radius: 32; color: "transparent"; border.color: "#207C65FF" }
                        Text { anchors.centerIn: parent; text: AppBridge.profile.initials || "É"; color: "white"; font.family: Theme.fontFamily; font.pixelSize: 27; font.weight: Font.Bold }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 6
                        Text { text: AppBridge.profile.name || "Votre profil"; color: "white"; font.family: Theme.fontFamily; font.pixelSize: 29; font.weight: Font.Bold; font.letterSpacing: -0.6; renderType: Text.NativeRendering }
                        Text { text: (AppBridge.profile.title || "") + ((AppBridge.profile.location || "") ? "  ·  " + AppBridge.profile.location : ""); color: "#CBC7D7"; font.pixelSize: 14 }
                        Text { text: AppBridge.profile.email || ""; color: Theme.accentBright; font.pixelSize: 12 }
                        Item { Layout.preferredHeight: 2 }
                        Text { Layout.fillWidth: true; Layout.maximumWidth: 700; text: AppBridge.profile.summary || ""; color: "#AAA7B5"; font.pixelSize: 12; wrapMode: Text.WordWrap; lineHeight: 1.2; maximumLineCount: 3; elide: Text.ElideRight }
                    }
                    ColumnLayout {
                        Text { text: String(AppBridge.profile.experiences || 0); color: "white"; font.pixelSize: 30; font.weight: Font.Bold; Layout.alignment: Qt.AlignHCenter }
                        Text { text: "EXPÉRIENCES"; color: "#8F8B9A"; font.pixelSize: 9; font.letterSpacing: 0.8 }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 46; color: "#3D3A48" }
                    ColumnLayout {
                        Text { text: String(AppBridge.profile.projects || 0); color: "white"; font.pixelSize: 30; font.weight: Font.Bold; Layout.alignment: Qt.AlignHCenter }
                        Text { text: "PROJETS"; color: "#8F8B9A"; font.pixelSize: 9; font.letterSpacing: 0.8 }
                    }
                }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 5
                columnSpacing: 16; rowSpacing: 16
                Surface {
                    Layout.columnSpan: 2
                    Layout.fillWidth: true
                    Layout.preferredHeight: 360
                    surfaceEndColor: "#1C1828"
                    SectionTitle { title: "Critères de recherche" }
                    FormLabel { text: "POSTES" }
                    Flow {
                        Layout.fillWidth: true; spacing: 7
                        Repeater { model: AppBridge.profile.target_roles || []; delegate: Pill { required property var modelData; text: modelData; tone: "accent"; compact: true } }
                    }
                    FormLabel { text: "CONTRATS & TÉLÉTRAVAIL" }
                    Flow {
                        Layout.fillWidth: true; spacing: 7
                        Repeater { model: (AppBridge.profile.contracts || []).concat(AppBridge.profile.remote_policies || []); delegate: Pill { required property var modelData; text: modelData; compact: true } }
                    }
                }
                Surface {
                    Layout.columnSpan: 3
                    Layout.fillWidth: true
                    Layout.preferredHeight: 360
                    surfaceEndColor: "#1C1828"
                    SectionTitle {
                        title: "Compétences"
                        caption: (AppBridge.profile.skill_categories || []).reduce(function(total, category) { return total + category.skills.length }, 0) + " compétences · " + (AppBridge.profile.skill_categories || []).length + " domaines"
                    }
                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentWidth: width
                        contentHeight: skillsContent.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: AppScrollBar { }
                        ColumnLayout {
                            id: skillsContent
                            width: parent.width
                            spacing: 12
                            Repeater {
                                model: AppBridge.profile.skill_categories || []
                                delegate: ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Text { text: modelData.name; color: Theme.inkSoft; font.pixelSize: 12; font.weight: Font.DemiBold }
                                    Flow {
                                        Layout.fillWidth: true; spacing: 6
                                        Repeater { model: modelData.skills; delegate: Pill { required property var modelData; text: modelData; compact: true } }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

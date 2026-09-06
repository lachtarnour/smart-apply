import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    signal navigateRequested(string route)
    function preferenceLabel(value) {
        var labels = {remote: "À distance", hybrid: "Hybride", onsite: "Sur site", "Full-time": "Temps plein", "Part-time": "Temps partiel"}
        return labels[value] || value
    }
    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight + 12
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: AppScrollBar { }
        ColumnLayout {
            id: content
            width: Math.min(parent.width - Theme.scrollGutter, 1320)
            x: (parent.width - Theme.scrollGutter - width) / 2
            spacing: Theme.pageGap
            PageHeader {
                Layout.fillWidth: true
                title: "Profil"
                AppButton { text: "Ouvrir le dossier"; iconSource: Theme.icon("folder"); onClicked: AppBridge.openProfileFolder() }
            }
            Surface {
                Layout.fillWidth: true
                surfaceEndColor: "#211B30"
                strokeColor: Theme.accentLine
                padding: 26
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 22
                    Rectangle {
                        Layout.preferredWidth: 66
                        Layout.preferredHeight: 66
                        Layout.alignment: Qt.AlignTop
                        radius: 20
                        color: Theme.accentSoft
                        border.color: Theme.accentLine
                        Text { anchors.centerIn: parent; text: AppBridge.profile.initials || "É"; color: Theme.accentBright; font.pixelSize: 23; font.weight: Font.DemiBold }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text { Layout.fillWidth: true; text: AppBridge.profile.name || "Votre profil"; color: Theme.ink; font.pixelSize: 25; font.weight: Font.Bold; wrapMode: Text.WordWrap }
                        Text { Layout.fillWidth: true; text: [AppBridge.profile.title, AppBridge.profile.location].filter(function(value) { return Boolean(value) }).join(" · "); color: Theme.inkSoft; font.pixelSize: 14; wrapMode: Text.WordWrap }
                        Text { Layout.fillWidth: true; text: AppBridge.profile.email || ""; visible: text.length > 0; color: Theme.accentBright; font.pixelSize: 13; wrapMode: Text.WrapAnywhere }
                        Text {
                            Layout.fillWidth: true
                            Layout.topMargin: 6
                            visible: text.length > 0
                            text: AppBridge.profile.summary || ""
                            color: Theme.inkMuted
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                            lineHeight: 1.35
                        }
                    }
                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop
                        Layout.preferredWidth: 120
                        spacing: 12
                        Repeater {
                            model: [
                                {count: AppBridge.profile.experiences || 0, label: "Expériences"},
                                {count: AppBridge.profile.projects || 0, label: "Projets"}
                            ]
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Text { text: modelData.count; color: Theme.ink; font.pixelSize: 20; font.weight: Font.DemiBold }
                                Text { Layout.fillWidth: true; text: modelData.label; color: Theme.inkMuted; font.pixelSize: 12 }
                            }
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sectionGap
                Surface {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 2
                    Layout.alignment: Qt.AlignTop
                    SectionTitle { title: "Critères de recherche" }
                    FormLabel { text: "POSTES" }
                    Flow {
                        id: rolesFlow
                        Layout.fillWidth: true
                        spacing: 7
                        Repeater {
                            model: AppBridge.profile.target_roles || []
                            delegate: Pill { required property var modelData; text: modelData; tone: "accent"; compact: true; width: Math.min(implicitWidth, rolesFlow.width) }
                        }
                    }
                    Text { visible: (AppBridge.profile.target_roles || []).length === 0; text: "Aucun poste renseigné"; color: Theme.inkMuted; font.pixelSize: 13 }
                    FormLabel { text: "CONTRATS ET TÉLÉTRAVAIL"; Layout.topMargin: 8 }
                    Flow {
                        id: preferencesFlow
                        Layout.fillWidth: true
                        spacing: 7
                        Repeater {
                            model: (AppBridge.profile.contracts || []).concat(AppBridge.profile.remote_policies || [])
                            delegate: Pill { required property var modelData; text: root.preferenceLabel(modelData); compact: true; width: Math.min(implicitWidth, preferencesFlow.width) }
                        }
                    }
                }
                Surface {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 3
                    Layout.alignment: Qt.AlignTop
                    SectionTitle {
                        title: "Compétences"
                    }
                    Repeater {
                        model: AppBridge.profile.skill_categories || []
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 9
                            Text { Layout.fillWidth: true; text: modelData.name; color: Theme.inkSoft; font.pixelSize: 13; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
                            Flow {
                                id: skillsFlow
                                Layout.fillWidth: true
                                spacing: 6
                                Repeater { model: modelData.skills; delegate: Pill { required property var modelData; text: modelData; compact: true; width: Math.min(implicitWidth, skillsFlow.width) } }
                            }
                        }
                    }
                    Text { visible: (AppBridge.profile.skill_categories || []).length === 0; text: "Aucune compétence renseignée"; color: Theme.inkMuted; font.pixelSize: 13 }
                }
            }
        }
    }
}

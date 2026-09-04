import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    signal navigateRequested(string route)

    function resetForm() {
        titleField.text = ""
        companyField.text = ""
        locationField.text = ""
        urlField.text = ""
        descriptionField.text = ""
    }

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
                title: "Ajouter une offre"
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 5
                columnSpacing: 16
                Surface {
                    Layout.columnSpan: 3
                    Layout.fillWidth: true
                    padding: 26
                    clip: true
                    surfaceEndColor: "#1B1725"
                    SectionTitle { title: "Offre" }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 12; rowSpacing: 7
                        FormLabel { text: "POSTE *" }
                        FormLabel { text: "ENTREPRISE *" }
                        AppField { id: titleField; Layout.fillWidth: true; placeholderText: "Machine Learning Engineer" }
                        AppField { id: companyField; Layout.fillWidth: true; placeholderText: "Nom de l’entreprise" }
                        FormLabel { text: "LOCALISATION"; Layout.columnSpan: 2 }
                        AppField { id: locationField; Layout.fillWidth: true; Layout.columnSpan: 2; placeholderText: "Paris, France" }
                    }
                    FormLabel { text: "LIEN DE L’OFFRE" }
                    AppField { id: urlField; Layout.fillWidth: true; placeholderText: "https://entreprise.com/jobs/…"; iconSource: Theme.icon("arrow-up-right") }
                    FormLabel { text: "DESCRIPTION COMPLÈTE *" }
                    AppTextArea { id: descriptionField; Layout.fillWidth: true; Layout.preferredHeight: 250; placeholderText: "Collez ici la description complète de l’offre…" }
                    ColumnLayout {
                        Layout.fillWidth: true
                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            AppButton { text: "Réinitialiser"; onClicked: root.resetForm() }
                            AppButton {
                                text: "Créer la candidature"; iconSource: Theme.icon("sparkle"); kind: "primary"; enabled: !AppBridge.busy
                                onClicked: AppBridge.createManualApplication(titleField.text, companyField.text, locationField.text, descriptionField.text, urlField.text)
                            }
                        }
                    }
                }
                ColumnLayout {
                    Layout.columnSpan: 2
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    spacing: 16
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 184
                        radius: 22; clip: true
                        border.color: "#4B435E"
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: "#18151F" }
                            GradientStop { position: 1; color: "#32284D" }
                        }
                        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 22; anchors.rightMargin: 22; anchors.top: parent.top; height: 1; color: "#2EFFFFFF" }
                        Canvas {
                            anchors.fill: parent; opacity: 0.25
                            onPaint: { var c = getContext("2d"); c.fillStyle = "#777084"; for (var x = 18; x < width; x += 27) for (var y = 18; y < height; y += 27) { c.beginPath(); c.arc(x, y, .8, 0, Math.PI * 2); c.fill() } }
                        }
                        Rectangle { width: 210; height: 210; radius: 105; x: parent.width - 130; y: -95; color: "#24735CFF" }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 24; spacing: 9
                            Rectangle { Layout.preferredWidth: 46; Layout.preferredHeight: 46; radius: 15; color: Theme.accentSoft; border.color: Theme.accentLine; SvgIcon { anchors.centerIn: parent; source: Theme.icon("sparkle"); color: Theme.accentBright; width: 22; height: 22 } }
                            Text { text: "Documents de candidature"; color: "white"; font.family: Theme.fontFamily; font.pixelSize: 22; font.weight: Font.Bold; font.letterSpacing: -0.4 }
                        }
                    }
                    Surface {
                        Layout.fillWidth: true
                        padding: 20
                        surfaceEndColor: "#1C1828"
                        SectionTitle { title: "Génération" }
                        Repeater {
                            model: [
                                {n: "01", t: "Analyse de l’offre"},
                                {n: "02", t: "Sélection du contenu"},
                                {n: "03", t: "Création du CV"},
                                {n: "04", t: "Création de la lettre"}
                            ]
                            delegate: Item {
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true
                                Layout.preferredHeight: 46
                                Rectangle {
                                    visible: index < 3
                                    x: 15; y: 34; width: 1; height: 19
                                    color: Theme.accentLine
                                }
                                Rectangle {
                                    x: 0; y: 2; width: 31; height: 31; radius: 10; color: Theme.accentSoft
                                    border.color: Theme.accentLine
                                    Text { anchors.centerIn: parent; text: modelData.n; color: Theme.accentDark; font.pixelSize: 10; font.weight: Font.Bold }
                                }
                                Text { x: 43; y: 10; width: parent.width - x; text: modelData.t; color: Theme.ink; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight }
                            }
                        }
                    }
                }
            }
        }
    }
}
